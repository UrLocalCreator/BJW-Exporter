import bpy,bmesh,os
from collections import defaultdict

bl_info={"name":"BJW Exporter(.bjw)","author":"UrLocalCreator","version":(1,0),"blender":(3,0,0),"location":"File>Export>BJW(.bjw)","description":"Exports objects to BJW Format","category":"Import-Export"}

def n(x):return int(x)if x==int(x)else f"{x:.7f}".rstrip('0').rstrip('.')

def wv(bm,i,mw,ev,sl):
    if not ev:return[],{},i
    o=[];m={}
    if sl:
        line=["v"]
        for v_ in bm.verts:
            t=mw@v_.co;m[v_.index]=i
            line.append(f"{n(t.x)} {n(t.z)} {n(-t.y)}");i+=1
        o.append(" ".join(line)+"\n")
    else:
        o.append("v\n")
        for v_ in bm.verts:
            t=mw@v_.co;m[v_.index]=i
            o.append(f"{n(t.x)} {n(t.z)} {n(-t.y)}\n");i+=1
    return o,m,i

def wu(bm,uvl,ui,ud,eu,sl):
    if not(eu and uvl):return[],ui
    o=[];nv=[]
    for f_ in bm.faces:
        for lp in f_.loops:
            uv=tuple(lp[uvl].uv)
            if uv not in ud:ud[uv]=ui;nv.append(uv);ui+=1
    if not nv:return o,ui
    if sl:
        l=["t"]
        for uv in nv:l.append(f"{n(uv[0])} {n(uv[1])}")
        o.append(" ".join(l)+"\n")
    else:
        o.append("t\n")
        for uv in nv:o.append(f"{n(uv[0])} {n(uv[1])}\n")
    return o,ui

def wf(bm,uvl,vm,ud,obj,es,eu,sl):
    from collections import defaultdict
    by=defaultdict(list)
    for f_ in bm.faces:
        s=1 if f_.smooth else 0
        m=f_.material_index
        by[(s,m)].append(f_)

    o=[]
    prev_s=None
    prev_m=None
    for (s,m),fc in by.items():
        tks=[]
        if es and s!=prev_s:
            tks.append(f"s {n(s)}")
            prev_s=s
        matn=""
        if m<len(obj.material_slots):
            slot=obj.material_slots[m].material
            if slot: matn=slot.name
        if m!=prev_m:
            if sl:
                tks.append(f" m {matn}")
            else:
                tks.append(f"m {matn}")
            prev_m=m
        tks.append("f")

        if sl:
            allf=[]
            for f_ in fc:
                idx=[]
                if eu and uvl:
                    for lp in f_.loops:
                        uvk=tuple(lp[uvl].uv)
                        u=ud.get(uvk,0)
                        idx.append(f"{vm[lp.vert.index]}/{u}")
                else:
                    for lp in f_.loops:
                        idx.append(f"{vm[lp.vert.index]}")
                allf.append(".".join(idx))

            o.append(" ".join(tks + [" ".join(allf)]))
        else:
            o.append(" ".join(tks) + "\n")
            for f_ in fc:
                idx=[]
                if eu and uvl:
                    for lp in f_.loops:
                        uvk=tuple(lp[uvl].uv)
                        u=ud.get(uvk,0)
                        idx.append(f"{vm[lp.vert.index]}/{u}")
                else:
                    for lp in f_.loops:
                        idx.append(f"{vm[lp.vert.index]}")
                o.append(".".join(idx) + "\n")
    return o

def proc(obj,ud,vi,ui,am,bd,ea,eu,es,ev,sl):
    out=[]
    if obj.type!="MESH":return out,vi,ui
    ms=obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh(preserve_all_data_layers=True)if am else obj.data
    bm=bmesh.new();bm.from_mesh(ms);bm.verts.ensure_lookup_table();bm.faces.ensure_lookup_table()
    out.append(f"o {obj.name}\n")
    vv,vm,vi=wv(bm,vi,obj.matrix_world,ev,sl);out+=vv
    uv_=bm.loops.layers.uv.active if eu else None
    uu,ui=wu(bm,uv_,ui,ud,eu,sl);out+=uu
    ff=wf(bm,uv_,vm,ud,obj,es,eu,sl);out+=ff
    if ea:
        pa=obj.parent
        if pa and pa.type=="ARMATURE":
            aw=pa.matrix_world
            vg={g.name:i for i,g in enumerate(obj.vertex_groups)}
            for b_ in pa.data.bones:
                if b_.name not in bd:
                    hw=aw@b_.head_local
                    bd[b_.name]={'parent':b_.parent.name if b_.parent else'','head':(hw.x,hw.z,-hw.y),'weights':{}}
                gi=vg.get(b_.name)
                if gi!=None:
                    for v_ in obj.data.vertices:
                        for gr in v_.groups:
                            if gr.group==gi:
                                w_=float(n(gr.weight))
                                if w_>0:bd[b_.name]['weights'].setdefault(vm[v_.index],0);bd[b_.name]['weights'][vm[v_.index]]+=w_
    bm.free()
    if am:obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()
    return out,vi,ui

class Export(bpy.types.Operator):
    bl_idname="export_mesh.custom_bjw"
    bl_label="Export BJW"
    filepath:bpy.props.StringProperty(subtype="FILE_PATH")
    thread_count:bpy.props.IntProperty(name="Thread Count",default=os.cpu_count(),min=1,max=os.cpu_count())
    apply_modifiers:bpy.props.BoolProperty(name="Apply Modifiers",default=False)
    export_armature:bpy.props.BoolProperty(name="Export Bones & Weights",default=True)
    export_uvs:bpy.props.BoolProperty(name="Export UVs",default=True)
    export_smooth:bpy.props.BoolProperty(name="Export Smooth Shading",default=True)
    export_vertices:bpy.props.BoolProperty(name="Export Vertices",default=True)
    export_single_line:bpy.props.BoolProperty(name="Compressed",default=False)
    def execute(self,c):
        if not self.filepath.lower().endswith(".bjw"):self.filepath+=".bjw"
        try:
            self.run(c)
            self.report({'INFO'},f"File exported to {self.filepath}")
            return{'FINISHED'}
        except Exception as e:
            self.report({'ERROR'},str(e));return{'CANCELLED'}
    def invoke(self,c,e):
        if not self.filepath:
            bn=bpy.path.basename(bpy.data.filepath).replace('.blend','')
            self.filepath=bpy.path.ensure_ext(bn if bn else'Untitled','.bjw')
        c.window_manager.fileselect_add(self);return{'RUNNING_MODAL'}
    def run(self,c):
        vi,ui=1,1;ud={};bd={}
        s=c.selected_objects if c.selected_objects else c.scene.objects
        c.window_manager.progress_begin(0,len(s))
        o=[]
        for i,o_ in enumerate(s):
            lines,vi,ui=proc(o_,ud,vi,ui,self.apply_modifiers,bd,
            self.export_armature,self.export_uvs,self.export_smooth,
            self.export_vertices,self.export_single_line)
            o+=lines;c.window_manager.progress_update(i+1)
        if self.export_armature:
            for bn,dt in bd.items():
                wts=dt['weights']
                if wts:
                    x,y,z=dt['head'];p=dt['parent']
                    wp=[f"{v}/{n(xx)}"for v,xx in wts.items()]
                    if self.export_single_line:o.append(f"b {bn}/{p}/{n(x)}/{n(y)}/{n(z)} w {' '.join(wp)}\n")
                    else:
                        o.append(f"b {bn}/{p}/{n(x)}/{n(y)}/{n(z)}\n");o.append("w\n")
                        for pair in wp:o.append(pair+"\n")
        c_=" ".join("".join(o).splitlines())if self.export_single_line else"".join(o)
        with open(self.filepath,'w')as f:f.write(c_.rstrip("\n"))
        c.window_manager.progress_end()

def menu_func_export(s,c):s.layout.operator(Export.bl_idname,text="BJW(.bjw)")

def register():
    bpy.utils.register_class(Export)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.utils.unregister_class(Export)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

if __name__=="__main__":register()
