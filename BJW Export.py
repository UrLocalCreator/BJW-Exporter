bl_info = {
    "name": "BJW Exporter (.bjw)",
    "author": "UrLocalCreator",
    "version": (1, 0),
    "blender": (3, 0, 0),
    "location": "File > Export > BJW (.bjw)",
    "description": "Exports objects to BJW Format",
    "category": "Import-Export",
}

import bpy
import bmesh
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

def number(num):
    return int(num) if num == int(num) else f"{num:.7f}".rstrip('0').rstrip('.')

# Global indices and locks
vertex_lock = Lock()
uv_lock = Lock()

def write_vertices(bm, global_vertex_index, matrix_world):
    output = []
    vertex_map = {}
    for vert in bm.verts:
        transformed_vert = matrix_world @ vert.co
        vertex_map[vert.index] = global_vertex_index
        output.append(f"{number(transformed_vert.x)} {number(transformed_vert.z)} {number(-transformed_vert.y)}\n")
        global_vertex_index += 1
    return output, vertex_map, global_vertex_index

def write_uvs(bm, uv_layer, global_uv_index, global_uv_dict):
    output = []
    if uv_layer:
        for face in bm.faces:
            for loop in face.loops:
                uv = tuple(loop[uv_layer].uv)
                if uv not in global_uv_dict:
                    global_uv_dict[uv] = global_uv_index
                    output.append(f"{number(uv[0])} {number(uv[1])}\n")
                    global_uv_index += 1
    return output, global_uv_index

def write_faces(bm, uv_layer, vertex_map, global_uv_dict, obj):
    output = []
    current_smooth, current_material = None, None
    for face in bm.faces:
        smooth = 1 if face.smooth else 0
        mat_idx = face.material_index
        mat_name = obj.material_slots[mat_idx].material.name if mat_idx < len(obj.material_slots) and obj.material_slots[mat_idx].material else ""

        if smooth != current_smooth or mat_name != current_material:
            output.append(f"s\n{number(smooth)}\nm\n{mat_name}\nf\n")
            current_smooth, current_material = smooth, mat_name

        face_indices = [f"{vertex_map[loop.vert.index]}/{global_uv_dict.get(tuple(loop[uv_layer].uv), 0)}" if uv_layer else f"{vertex_map[loop.vert.index]}" for loop in face.loops]
        output.append(".".join(face_indices) + "\n")
    return output

def process_object(obj, global_uv_dict, global_vertex_index, global_uv_index, apply_modifiers, bones_data):
    output = []

    def collect_bones_and_weights(obj, vertex_map):
        if obj.parent and obj.parent.type == 'ARMATURE':
            armature = obj.parent
            armature_matrix_world = armature.matrix_world

            bone_to_group = {group.name: idx for idx, group in enumerate(obj.vertex_groups)}

            for bone in armature.data.bones:
                if bone.name not in bones_data:
                    head_world = armature_matrix_world @ bone.head_local
                    head_adjusted = (head_world.x, head_world.z, -head_world.y)
                    parent = bone.parent.name if bone.parent else ""
                    bones_data[bone.name] = {
                        "parent": parent,
                        "head": head_adjusted,
                        "weights": []
                    }

                group_index = bone_to_group.get(bone.name)
                if group_index is not None:
                    for vertex in obj.data.vertices:
                        for group in vertex.groups:
                            if group.group == group_index and float(number(group.weight)) > 0:
                                bones_data[bone.name]["weights"].append(f"{vertex_map[vertex.index]}/{number(group.weight)}")

    if obj.type != 'MESH':
        return [], global_vertex_index, global_uv_index

    temp_mesh = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh(preserve_all_data_layers=True) if apply_modifiers else obj.data

    bm = bmesh.new()
    bm.from_mesh(temp_mesh)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    output.append(f"o\n{obj.name}\n")
    vertex_data, vertex_map, global_vertex_index = write_vertices(bm, global_vertex_index, obj.matrix_world)
    output.append("v\n" + "".join(vertex_data))
    uv_layer = bm.loops.layers.uv.active
    uv_data, global_uv_index = write_uvs(bm, uv_layer, global_uv_index, global_uv_dict)
    if uv_data:
        output.append("t\n" + "".join(uv_data))
    output.extend(write_faces(bm, uv_layer, vertex_map, global_uv_dict, obj))
    collect_bones_and_weights(obj, vertex_map)
    bm.free()

    if apply_modifiers:
        obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()

    return output, global_vertex_index, global_uv_index

class Export(bpy.types.Operator):
    bl_idname = "export_mesh.custom_bjw"
    bl_label = "Export BJW"
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    thread_count: bpy.props.IntProperty(name="Thread Count", default=os.cpu_count(), min=1, max=os.cpu_count(), description="Number of threads to use for export")
    apply_modifiers: bpy.props.BoolProperty(name="Apply Modifiers", default=False, description="Apply geometry modifiers during export")

    def execute(self, context):
        if not self.filepath.lower().endswith(".bjw"):
            self.filepath += ".bjw"
        try:
            self.export_custom_format(context)
            self.report({'INFO'}, f"File exported to {self.filepath}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

    def invoke(self, context, event):
        if not self.filepath:
            blend_name = bpy.path.basename(bpy.data.filepath).replace('.blend', '')
            self.filepath = bpy.path.ensure_ext(blend_name if blend_name else "Untitled", ".bjw")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def export_custom_format(self, context):
        global_vertex_index = 1
        global_uv_index = 1
        global_uv_dict = {}
        bones_data = {}
        objects_to_export = context.selected_objects if context.selected_objects else context.scene.objects
        context.window_manager.progress_begin(0, len(objects_to_export))

        try:
            with open(self.filepath, 'w') as file:
                for idx, obj in enumerate(objects_to_export):
                    output, global_vertex_index, global_uv_index = process_object(obj, global_uv_dict, global_vertex_index, global_uv_index, self.apply_modifiers, bones_data)
                    file.write("".join(output))
                    context.window_manager.progress_update(idx + 1)

                # Write combined bones and weights at the end
                for bone_name, bone_data in bones_data.items():
                    if bone_data["weights"]:
                        head_adjusted = bone_data["head"]
                        parent = bone_data["parent"]
                        file.write(f"b\n{bone_name}/{parent}/{number(head_adjusted[0])}/{number(head_adjusted[1])}/{number(head_adjusted[2])}\n")
                        file.write("w\n" + "\n".join(bone_data["weights"]) + "\n")
        finally:
            context.window_manager.progress_end()

def menu_func_export(self, context):
    self.layout.operator(Export.bl_idname, text="BJW (.bjw)")

def register():
    bpy.utils.register_class(Export)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.utils.unregister_class(Export)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

if __name__ == "__main__":
    register()
