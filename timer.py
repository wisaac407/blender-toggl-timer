import bpy

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
    bl_label = "Layout Demo"
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
