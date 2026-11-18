import numpy as np,struct,json,io,os,glob,sys,time,copy
from PIL import Image
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SRC=ROOT/'sources';DEST=ROOT/'assets';DEST.mkdir(parents=True,exist_ok=True)
SOURCES={
'mannequin':'manequim de tecido 3d modelo-2.glb',
'overalls_cream':'cream overalls 3d model.glb',
'jacket_cream':'cream short sleeve jacket 3d model.glb',
'pants_cargo':'cargo pants 3d model.glb',
'pants_black':'black cargo pants 3d model.glb',
'cap_camo':'camouflage cap 3d model.glb',
'cap_plaid':'plaid cap 3d model.glb',
'cap_leopard':'leopard print cap 3d model-2.glb',
}

# --- Mannequin pose -----------------------------------------------------------
# The source mannequin stands with its arms hanging straight down, touching the
# torso. Every top (jacket, overalls...) then cuts through the upper arm: the
# arm passes through the side wall of the garment instead of going into the
# sleeve. Like posing an armature in Blender, the arms are rotated outwards
# around the shoulder joint (linear blend skinning, smooth weights between the
# armpit and the top of the shoulder). The mannequin is a single mesh, so the
# arm is selected by the air gap that separates it from the torso.
ARM_ABDUCTION_DEG=15.0
# Shoulder joint, fractions of the source height (also used by fitting-room.html).
ARM_PIVOT_Y=.765;ARM_PIVOT_X=.118
def _smooth(a,b,x):
 t=np.clip((x-a)/(b-a),0,1);return t*t*(3-2*t)
# --- Head proportion ------------------------------------------------------------
# The source head spans ~15% of the figure (about 6.7 heads tall, head 39% of the
# shoulder width), which reads as a doll. Adults are ~7.5 heads (13.3%). The head is
# scaled uniformly around the top of the neck, blending through the neck so the
# junction stays smooth. Total height drops a little; the fitting room anchors its
# scale on SOURCE_MANNEQUIN_HEIGHT (the original height), so garment calibration is
# unchanged.
HEAD_SCALE=0.88
def shrink_head(pos):
 H=float(pos[:,1].max()-pos[:,1].min());y0=float(pos[:,1].min())
 h=(pos[:,1]-y0)/H
 w=_smooth(.832,.862,h)
 if not (w>0).any():return pos
 # Pivot: centre of the neck at its narrowest section.
 neck=pos[np.abs(h-.845)<.004]
 neck=neck[np.abs(neck[:,0])<.07*H/0.9795]
 piv=np.array([0.0,y0+.845*H,float(neck[:,2].mean())],dtype=np.float64)
 k=(1-w*(1-HEAD_SCALE))[:,None]
 return (piv+(pos-piv)*k).astype(np.float32)

def pose_arms(pos,nor):
 H=float(pos[:,1].max()-pos[:,1].min());y0=float(pos[:,1].min())
 h=(pos[:,1]-y0)/H;ax=np.abs(pos[:,0])
 # x of the gap between arm and torso, measured on the source mesh (fraction of height -> x/H).
 split=np.interp(h,[.385,.52,.56,.62,.66,.70],[.112,.112,.103,.092,.091,.095])*H/0.9795
 arm_w=_smooth(split-.006*H,split+.006*H,ax)
 # Fade the rotation in from the top of the shoulder down to the armpit.
 w=arm_w*(1-_smooth(.665,.775,h))*(h>.37)
 # Shoulder joint (pivot), per side.
 py=y0+ARM_PIVOT_Y*H;px=ARM_PIVOT_X*H/0.9795
 out_p=pos.copy();out_n=nor.copy()
 for side in(1,-1):
  sel=(np.sign(pos[:,0])==side)&(w>0)
  if not sel.any():continue
  a=np.deg2rad(ARM_ABDUCTION_DEG)*side*w[sel]
  c,s_=np.cos(a),np.sin(a)
  dx=pos[sel,0]-side*px;dy=pos[sel,1]-py
  out_p[sel,0]=side*px+dx*c-dy*s_;out_p[sel,1]=py+dx*s_+dy*c
  nx,ny=nor[sel,0],nor[sel,1]
  out_n[sel,0]=nx*c-ny*s_;out_n[sel,1]=nx*s_+ny*c
 return out_p.astype(np.float32),out_n.astype(np.float32),arm_w*(h>.37),w

def optimize(key,path):
 t=time.monotonic();orig=(SRC/path).read_bytes();jlen=struct.unpack_from('<I',orig,12)[0];j=json.loads(orig[20:20+jlen]);binoff=20+jlen+8
 prim=j['meshes'][0]['primitives'][0]
 def attr(index):
  a=j['accessors'][index];view=j['bufferViews'][a['bufferView']];n={'VEC3':3,'VEC2':2,'SCALAR':1}[a['type']];dt={5126:'<f4',5125:'<u4',5123:'<u2'}[a['componentType']];return np.frombuffer(orig,dtype=dt,count=a['count']*n,offset=binoff+view.get('byteOffset',0)+a.get('byteOffset',0)).reshape(-1,n)
 pos=attr(prim['attributes']['POSITION']).copy();nor=attr(prim['attributes']['NORMAL']).copy();uv=attr(prim['attributes']['TEXCOORD_0']).copy();faces=attr(prim['indices']).reshape(-1,3).astype(np.int32,copy=False)
 arm=None;armw=None
 if key=='mannequin':
  pos,nor,arm,armw=pose_arms(pos,nor)
  pos=shrink_head(pos)
 # Spatial + UV grouping to preserve material seams. A conservative quantized voxel grid maintains the silhouette while reducing ~1M verts to ~60-120k.
 step=.0055 if key=='mannequin' else (.006 if key.startswith('cap') else .0065)
 qpos=np.round(pos/step).astype(np.int32)
 quv=np.round(uv/.055).astype(np.int32)
 # Position comes ONLY from the spatial cluster. Previously the cluster key also
 # contained the UV, so both sides of a UV seam were averaged separately, landed
 # in slightly different places and opened cracks through which the mannequin
 # showed. Now every UV variant of a spatial cluster shares the exact same point.
 _,pinv=np.unique(qpos,axis=0,return_inverse=True);pinv=pinv.reshape(-1)
 pn=int(pinv.max())+1
 pcount=np.bincount(pinv,minlength=pn).astype(np.float64)
 def pavg(src):return np.column_stack([np.bincount(pinv,weights=src[:,k],minlength=pn)/pcount for k in range(src.shape[1])]).astype(np.float32)
 cluster_pos=pavg(pos);cluster_nor=pavg(nor)
 cluster_nor/=np.maximum(np.linalg.norm(cluster_nor,axis=1,keepdims=True),1e-8)
 keys=np.column_stack((pinv,quv))
 unique,inv=np.unique(keys,axis=0,return_inverse=True);inv=inv.reshape(-1)
 n=len(unique)
 count=np.bincount(inv,minlength=n).astype(np.float64)
 def avg(src):return np.column_stack([np.bincount(inv,weights=src[:,k],minlength=n)/count for k in range(src.shape[1])]).astype(np.float32)
 owner=unique[:,0]
 pnew=cluster_pos[owner];nnew=cluster_nor[owner];unew=avg(uv)
 anew=avg(arm.reshape(-1,1)).reshape(-1) if arm is not None else None
 wnew=avg(armw.reshape(-1,1)).reshape(-1) if armw is not None else None
 # Degenerate test on the spatial cluster: a triangle collapsed in space is dropped
 # even if its corners kept different UV variants.
 mapped=inv[faces];pm=pinv[faces]
 keep=(pm[:,0]!=pm[:,1])&(pm[:,1]!=pm[:,2])&(pm[:,0]!=pm[:,2]);mapped=mapped[keep].astype(np.uint32,copy=False)
 # Remove degenerate triangles formed by vertex clustering and repeated triangles within the same face.
 mapped=np.unique(mapped,axis=0)
 # Remove unused vertices for smaller output
 used,rerank=np.unique(mapped,return_inverse=True)
 pnew=pnew[used];nnew=nnew[used];unew=unew[used];mapped=rerank.reshape(-1,3).astype('<u4')
 if anew is not None:anew=anew[used].astype(np.float32);wnew=wnew[used].astype(np.float32)
 print(key,'verts',len(pos),'->',len(pnew),'tri',len(faces),'->',len(mapped),'preprocess',round(time.monotonic()-t,1),flush=True)
 buffers=bytearray();views=[];acc=[];images=[]
 def appendbuf(data):
  nonlocal buffers
  while len(buffers)%4:buffers.append(0)
  off=len(buffers);buffers+=data
  views.append({'buffer':0,'byteOffset':off,'byteLength':len(data)})
  return len(views)-1
 streams=[('POSITION',pnew,5126,'VEC3'),('NORMAL',nnew,5126,'VEC3'),('TEXCOORD_0',unew,5126,'VEC2'),('indices',mapped.reshape(-1,1),5125,'SCALAR')]
 # Mannequin only: per-vertex arm weight (custom glTF attribute _ARM, loaded by three.js
 # as "_arm"). The fitting room uses it to know which garments may touch the arms.
 # _ARMW: full skinning weight of the arm pose (shoulder fade included), used by the
 # fitting room to open the arms further for wide sleeves.
 if anew is not None:streams+=[('_ARM',anew.reshape(-1,1),5126,'SCALAR'),('_ARMW',wnew.reshape(-1,1),5126,'SCALAR')]
 for name,arr,comp,typ in streams:
  idx=appendbuf(arr.tobytes());entry={'bufferView':idx,'componentType':comp,'count':len(arr),'type':typ}
  if name=='POSITION':entry.update({'max':pnew.max(axis=0).tolist(),'min':pnew.min(axis=0).tolist()})
  acc.append(entry)
 for img in j['images']:
  bview=j['bufferViews'][img['bufferView']];source=orig[binoff+bview['byteOffset']:binoff+bview['byteOffset']+bview['byteLength']]
  im=Image.open(io.BytesIO(source)).convert('RGB')
  size=1280 if key.startswith('cap') else 1024
  im.thumbnail((size,size),Image.Resampling.LANCZOS)
  raw=io.BytesIO()
  im.save(raw,format='JPEG',quality=83,optimize=True,subsampling=0 if 'basecolor' in img['name'] else 2)
  images.append({'bufferView':appendbuf(raw.getvalue()),'mimeType':'image/jpeg'})
 out={
 'asset':{'version':'2.0','generator':'DOTH optimized original Tripo mesh assets'},
 'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'mesh':0,'name':key}],
 'buffers':[{'byteLength':len(buffers)}],'bufferViews':views,'accessors':acc,
 'images':images,'textures':copy.deepcopy(j['textures']),'samplers':copy.deepcopy(j.get('samplers',[])),
 'materials':copy.deepcopy(j['materials']),
 'meshes':[{'primitives':[{'attributes':dict({'POSITION':0,'NORMAL':1,'TEXCOORD_0':2},**({'_ARM':4,'_ARMW':5} if anew is not None else {})),'indices':3,'material':0,'mode':4}]}]
 }
 # normalTexture remains supported, images are JPEG after conversion.
 jbytes=json.dumps(out,separators=(',',':'),ensure_ascii=True).encode()
 while len(jbytes)%4:jbytes+=b' '
 while len(buffers)%4:buffers.append(0)
 size=12+8+len(jbytes)+8+len(buffers)
 glb=struct.pack('<4sII',b'glTF',2,size)+struct.pack('<I4s',len(jbytes),b'JSON')+jbytes+struct.pack('<I4s',len(buffers),b'BIN\0')+buffers
 dst=DEST/f'{key}.glb';dst.write_bytes(glb)
 print('saved',dst.name,round(dst.stat().st_size/1e6,2),'MB','time',round(time.monotonic()-t,1),flush=True)
 return {'key':key,'vertices':int(len(pnew)),'triangles':int(len(mapped)),'bytes':len(glb)}

if __name__=='__main__':
 only=set(sys.argv[1:])
 results=[]
 for key,filename in SOURCES.items():
  if only and key not in only:continue
  results.append(optimize(key,filename))
 if only:sys.exit(0)
 (DEST/'manifest.json').write_text(json.dumps(results,indent=2))
