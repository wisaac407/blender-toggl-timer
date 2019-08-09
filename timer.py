import concurrent
import gc
import sys
import asyncio
import bpy

bl_info = {
    "name": "Toggl Timer",
    "author": "Isaac Weaver",
    "version": (0, 0, 1),
    "blender": (2, 80, 0),
    "location": "Properties > Scene > Timer",
    "description": "Integrate Toggl timer into Blender",
    "warning": "For demonstration only",
    "wiki_url": "",
    "category": "Productivity",
}


class EventLoop:
    """Main event loop"""

    _loop = None
    _operator = None
    _stop_next_step = None

    def start(self, operator: bpy.types.Operator):
        # Store a copy of our own event loop rather than use asyncio.get_event_loop so we
        # aren't fighting with other addons that use asyncio (e.g. the Blender Cloud addon)
        if sys.platform == 'win32':
            # On Windows, the default event loop is SelectorEventLoop, which does
            # not support subprocesses. ProactorEventLoop should be used instead.
            # Source: https://docs.python.org/3/library/asyncio-subprocess.html
            self._loop = asyncio.ProactorEventLoop()
        else:
            self._loop = asyncio.new_event_loop()

            # Prevent subprocesses from hanging: https://github.com/python/asyncio/issues/478
            asyncio.get_child_watcher().attach_loop(self._loop)

        self._operator = operator

        # Needed to run HTTP requests
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
        self._loop.set_default_executor(executor)

        def handle_exception(loop, context):
            exc = context.get('exception')
            # Most places that raise an error will take care of reporting the error,
            # so for now just log it out and close the event loop.
            import traceback
            traceback.print_tb(exc.__traceback__)
            self.report({'ERROR'}, 'Stopping because of error: {}: {}'.format(type(exc).__name__, exc))

            # We can't actually stop here, we have to wait until the next step
            self._stop_next_step = True

        self._loop.set_exception_handler(handle_exception)

    def get_loop(self) -> asyncio.AbstractEventLoop:
        """Return the asyncio event loop"""
        return self._loop

    def step(self):
        """Execute single step of the event loop"""
        self._loop.call_soon(self._loop.stop)
        self._loop.run_forever()

        if self._stop_next_step:
            self._stop_next_step = False
            self.stop()

    def stop(self):
        """Stop the event loop"""
        logger.debug('Stopping event loop')
        self._loop.close()
        self._loop = None
        self._operator = None

        # TODO: Check that this is needed (maybe check that it returns non-zero?)
        gc.collect()

    def dispatch(self, action):
        """Add 'action' to the event loop"""
        if self.running:
            asyncio.ensure_future(action, loop=self._loop)

    def report(self, *args, **kwargs):
        """Pass through for the modal report function"""
        if self._operator:
            self._operator.report(*args, **kwargs)

    @property
    def running(self) -> bool:
        """True if the event loop is currently running"""
        return self._loop is not None and not self._loop.is_closed()


class Manager:
    pass


classes = ()


def register_class(cls):
    global classes
    classes += (cls,)
    return cls


@register_class
class Task(bpy.types.PropertyGroup):
    """Single task"""
    name: bpy.props.StringProperty()
    complete: bpy.props.BoolProperty()


@register_class
class TimerProps(bpy.types.PropertyGroup):
    tasks: bpy.props.CollectionProperty(type=Task)
    active_task_index: bpy.props.IntProperty()


@register_class
class TimerAddTask(bpy.types.Operator):
    """Add a task"""
    bl_idname = "timer.add_task"
    bl_label = "Add Task"

    task: bpy.props.StringProperty()

    def execute(self, context):
        timer = context.scene.timer
        task = timer.tasks.add()
        task.name = self.task
        return {"FINISHED"}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "task")


@register_class
class TimerRemoveTask(bpy.types.Operator):
    """Remove current task"""
    bl_idname = "timer.remove_task"
    bl_label = "Remove Task"

    @classmethod
    def poll(cls, context):
        timer = context.scene.timer
        return len(timer.tasks) > 0

    def execute(self, context):
        timer = context.scene.timer
        timer.tasks.remove(timer.active_task_index)
        if timer.active_task_index >= len(timer.tasks):
            timer.active_task_index = len(timer.tasks) - 1
        return {"FINISHED"}


@register_class
class TimerMoveTask(bpy.types.Operator):
    """Move task up or down"""

    bl_idname = "timer.move_task"
    bl_label = "Move task"

    direction: bpy.props.EnumProperty(items=[
        ('UP', 'Up', 'Move one position up'),
        ('DOWN', 'Down', 'Move one position down')
    ])

    @classmethod
    def poll(cls, context):
        timer = context.scene.timer
        return len(timer.tasks) > 0

    def execute(self, context):
        timer = context.scene.timer

        delta = 1 if self.direction == 'DOWN' else -1
        target = timer.active_task_index + delta
        target = max(min(target, len(timer.tasks) - 1), 0)

        timer.tasks.move(timer.active_task_index, target)
        timer.active_task_index = target

        return {'FINISHED'}


@register_class
class TIMER_UL_tasks(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            if item.complete:
                layout.active = False

            row = layout.row()
            row.prop(item, "complete", text="", emboss=True)
            row.prop(item, "name", text="", emboss=False, icon_value=icon)

        # 'GRID' layout type should be as compact as possible (typically a single icon!).
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon_value=icon)


@register_class
class Timer(bpy.types.Panel):
    """Creates a Panel in the scene context of the properties editor"""
    bl_label = "Toggl Timer"
    bl_idname = "SCENE_PT_layout"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout
        timer = context.scene.timer
        row = layout.row()
        col = row.column()
        col.template_list("TIMER_UL_tasks", "", timer, "tasks", timer, "active_task_index")

        col = row.column(align=True)
        col.operator('timer.add_task', text="", icon="ADD")
        col.operator('timer.remove_task', text="", icon="REMOVE")

        col.separator()
        col.operator('timer.move_task', text="", icon="TRIA_UP").direction = 'UP'
        col.operator('timer.move_task', text="", icon="TRIA_DOWN").direction = 'DOWN'


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.timer = bpy.props.PointerProperty(type=TimerProps)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
