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

def number(num):
    return f"{num:.16g}"

class Export(bpy.types.Operator):
    bl_idname = "export_mesh.custom_bjw"
    bl_label = "Export BJW"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

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
            self.filepath = bpy.path.ensure_ext("Untitled", ".bjw")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def export_custom_format(self, context):
        with open(self.filepath, 'w') as file:
            obj = bpy.context.active_object

            if obj is None or obj.type != 'MESH':
                raise ValueError("No active mesh object found.")

            mesh = obj.data
            bm = bmesh.new()
            bm.from_mesh(mesh)
            bm.verts.ensure_lookup_table()
            bm.faces.ensure_lookup_table()

            file.write("l\n")
            for mat_slot in obj.material_slots:
                if mat_slot.material and mat_slot.material.name:
                    file.write(f"{mat_slot.material.name}.mtl\n")

            file.write("o\n")
            file.write(f"{obj.name}\n")

            file.write("v\n")
            for vert in bm.verts:
                x, y, z = vert.co.x, vert.co.y, vert.co.z
                file.write(f"{number(x)} {number(z)} {number(-y)}\n")

            uv_layer = bm.loops.layers.uv.active
            if uv_layer:
                file.write("t\n")
                uv_dict = {}
                uv_index = 1
                for face in bm.faces:
                    for loop in face.loops:
                        uv = tuple(loop[uv_layer].uv)
                        if uv not in uv_dict:
                            uv_dict[uv] = uv_index
                            file.write(f"{number(uv[0])} {number(uv[1])}\n")
                            uv_index += 1

            smooth = 1 if all(face.smooth for face in bm.faces) else 0
            file.write("s\n")
            file.write(f"{smooth}\n")

            file.write("m\n")
            for mat_slot in obj.material_slots:
                file.write(f"{mat_slot.name}\n")

            file.write("f\n")
            for face in bm.faces:
                face_indices = []
                for loop in face.loops:
                    v_idx = loop.vert.index + 1
                    uv = tuple(loop[uv_layer].uv) if uv_layer else None
                    uv_idx = uv_dict[uv] if uv_layer and uv in uv_dict else 0
                    face_indices.append(f"{v_idx}/{uv_idx}")
                file.write(".".join(face_indices) + "\n")

            armature = next((mod.object for mod in obj.modifiers if mod.type == 'ARMATURE'), None)
            if armature and armature.type == 'ARMATURE':
                file.write("b\n")
                for bone in armature.data.bones:
                    parent_name = bone.parent.name if bone.parent else "None"
                    head = bone.head_local
                    file.write(f"{bone.name}/{parent_name}/{number(head.x)}/{number(head.y)}/{number(head.z)}\n")

                file.write("w\n")
                for vert in mesh.vertices:
                    weights = [(g.group, g.weight) for g in vert.groups]
                    if weights:
                        weights_str = " ".join([f"{g}/{number(w)}" for g, w in weights])
                        file.write(f"{vert.index + 1} {weights_str}\n")

            bm.free()

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
