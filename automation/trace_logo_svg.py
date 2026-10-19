import numpy as np, potrace, math
from PIL import Image
from scipy import ndimage as nd
S=3
im=Image.open('/workspace/fcb-wt-lightreal/logo-light.png').convert('RGBA')
W,H=im.size
big=np.array(im.resize((W*S,H*S),Image.LANCZOS)).astype(float)
A=big[...,3]; rgb=big[...,:3]; L=0.299*rgb[...,0]+0.587*rgb[...,1]+0.114*rgb[...,2]
mx=rgb.max(2); mn=rgb.min(2); sat=(mx-mn)/(mx+1e-6)
solid=A>110
dark=solid&(L<75)&(sat<0.5)
color=solid&~dark
# clarity: slightly heavier dark strokes, fill pinholes, drop specks
dark=nd.binary_dilation(dark,iterations=1)
dark=nd.binary_closing(dark,iterations=1)
color=nd.binary_closing(color,iterations=1)
def clean(m,minpx):
    lab,n=nd.label(m); sz=nd.sum(m,lab,range(1,n+1)); return np.isin(lab,1+np.where(sz>=minpx)[0])
dark=clean(dark,40); color=clean(color,60)
# tagline periods: make the small dots on the tagline row bolder so they survive at 44px
lab,n=nd.label(dark); sz=nd.sum(dark,lab,range(1,n+1)); cy=np.array(nd.center_of_mass(dark,lab,range(1,n+1)))[:,0]
dots=np.isin(lab,1+np.where((sz<60*S*S)&(cy>340*S))[0])
dark=dark|nd.binary_dilation(dots,iterations=2*S)
def path(mask):
    bm=potrace.Bitmap(~mask)
    pl=bm.trace(turdsize=8,turnpolicy=potrace.POTRACE_TURNPOLICY_MINORITY,alphamax=1.0,opticurve=True,opttolerance=0.6)
    out=[]
    f=lambda p:f'{p.x/S:.1f} {p.y/S:.1f}'
    for c in pl:
        d=['M'+f(c.start_point)]
        for s in c.segments:
            if s.is_corner: d.append('L'+f(s.c)+' L'+f(s.end_point))
            else: d.append('C'+f(s.c1)+' '+f(s.c2)+' '+f(s.end_point))
        out.append(''.join(d)+'Z')
    return ''.join(out)
pd=path(dark); pc=path(color)
ang=math.radians(100); dx,dy=math.sin(ang),-math.cos(ang)
Lh=(W*abs(dx)+H*abs(dy))/2; cx,cy=W/2,H/2
x1,y1,x2,y2=cx-Lh*dx,cy-Lh*dy,cx+Lh*dx,cy+Lh*dy
svg=f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="Full Court Buckets"><title>Full Court Buckets</title><defs><linearGradient id="fcb-g" gradientUnits="userSpaceOnUse" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"><stop offset="0" stop-color="#5b22c9"/><stop offset=".45" stop-color="#7d35ff"/><stop offset="1" stop-color="#f10091"/></linearGradient></defs><path fill="url(#fcb-g)" fill-rule="evenodd" d="{pc}"/><path fill="#151413" fill-rule="evenodd" d="{pd}"/><!--DOTS--></svg>'''
open('logo.svg','w').write(svg); print(len(svg))
