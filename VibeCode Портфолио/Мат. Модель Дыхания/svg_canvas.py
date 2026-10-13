"""Небольшой SVG → Tkinter Canvas renderer (только стандартная библиотека).

Геометрия одна и та же для браузерной и оконной версии. JavaScript в Tkinter
НЕ выполняется: перемещения, анимация и отрисовка здесь полностью на Python.
Поддерживается подмножество SVG, используемое в учебной схеме.
"""
from __future__ import annotations

from bisect import bisect_right
from functools import lru_cache
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from model import lung_expansion, inspired_air_rate

NUM = r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?"
IDENTITY = (1., 0., 0., 1., 0., 0.)


def multiply(m, n):
    a,b,c,d,e,f = m
    A,B,C,D,E,F = n
    return (a*A+c*B, b*A+d*B, a*C+c*D, b*C+d*D,
            a*E+c*F+e, b*E+d*F+f)


def transform_point(m, x, y):
    a,b,c,d,e,f = m
    return a*x+c*y+e, b*x+d*y+f


def parse_transform(value: str):
    m = IDENTITY
    for name, args in re.findall(r"(\w+)\(([^)]*)\)", value):
        v = [float(s) for s in re.findall(NUM, args)]
        n = IDENTITY
        if name == "translate":
            n = (1,0,0,1,v[0],v[1] if len(v)>1 else 0)
        elif name == "scale":
            n = (v[0],0,0,v[1] if len(v)>1 else v[0],0,0)
        elif name == "rotate":
            angle = math.radians(v[0]); c = math.cos(angle); s = math.sin(angle)
            n = (c,s,-s,c,0,0)
            if len(v) == 3:
                n = multiply(multiply((1,0,0,1,v[1],v[2]),n),
                             (1,0,0,1,-v[1],-v[2]))
        elif name == "matrix" and len(v) == 6:
            n = tuple(v)
        m = multiply(m,n)
    return m


@lru_cache(maxsize=256)
def flatten_path(data: str):
    tokens = re.findall(r"[A-Za-z]|" + NUM, data)
    result = []; points = []; x = y = 0.; start = (0.,0.); previous = ""; control = None
    command = ""; i = 0
    counts = {"M":2,"L":2,"H":1,"V":1,"C":6,"S":4,"Q":4,"T":2}
    while i < len(tokens):
        if tokens[i].isalpha():
            command = tokens[i]; i += 1
            if command.upper() == "Z":
                if points:
                    points.append(start); result.append((tuple(points),True)); points=[]
                x,y = start; previous="Z"; control=None
                continue
        upper = command.upper(); relative = command.islower()
        count = counts.get(upper)
        if count is None or i+count>len(tokens):
            raise ValueError(f"Неподдерживаемый SVG path: {command}")
        v = [float(s) for s in tokens[i:i+count]]; i += count
        old = (x,y)
        def coord(j):
            return (v[j]+(x if relative else 0), v[j+1]+(y if relative else 0))
        if upper == "M":
            if points: result.append((tuple(points),False))
            x,y=coord(0); start=(x,y); points=[start]
            command="l" if relative else "L"; control=None
        elif upper == "L":
            x,y=coord(0); points.append((x,y)); control=None
        elif upper == "H":
            x=v[0]+(x if relative else 0); points.append((x,y)); control=None
        elif upper == "V":
            y=v[0]+(y if relative else 0); points.append((x,y)); control=None
        elif upper in ("C","S"):
            if upper == "C": p1,p2,end=coord(0),coord(2),coord(4)
            else:
                p1=(2*x-control[0],2*y-control[1]) if previous in ("C","S") and control else old
                p2,end=coord(0),coord(2)
            for j in range(1,21):
                t=j/20; a=1-t
                points.append((a**3*x+3*a*a*t*p1[0]+3*a*t*t*p2[0]+t**3*end[0],
                               a**3*y+3*a*a*t*p1[1]+3*a*t*t*p2[1]+t**3*end[1]))
            x,y=end; control=p2
        elif upper in ("Q","T"):
            if upper == "Q": p1,end=coord(0),coord(2)
            else:
                p1=(2*x-control[0],2*y-control[1]) if previous in ("Q","T") and control else old
                end=coord(0)
            for j in range(1,17):
                t=j/16; a=1-t
                points.append((a*a*x+2*a*t*p1[0]+t*t*end[0],
                               a*a*y+2*a*t*p1[1]+t*t*end[1]))
            x,y=end; control=p1
        previous=upper
    if points: result.append((tuple(points),False))
    return tuple(result)


class Polyline:
    def __init__(self, data: str):
        self.points = [point for subpath,_ in flatten_path(data) for point in subpath]
        self.distances = [0.]
        for a,b in zip(self.points,self.points[1:]):
            self.distances.append(self.distances[-1]+math.hypot(b[0]-a[0],b[1]-a[1]))
        self.length = self.distances[-1]

    def at(self, distance: float):
        distance = max(0,min(self.length,distance))
        i = min(len(self.points)-2,max(0,bisect_right(self.distances,distance)-1))
        a,b=self.points[i],self.points[i+1]; span=self.distances[i+1]-self.distances[i]
        q=(distance-self.distances[i])/span if span else 0
        return a[0]+q*(b[0]-a[0]),a[1]+q*(b[1]-a[1])


def blend(colour: str, opacity: float = 1., background: str = "#ffffff"):
    if colour in ("none","",None): return ""
    if colour.startswith("url"):
        colour={"url(#lung-fill)":"#e5f1e7", "url(#alveolus-fill)":"#edf7ee",
                "url(#exchange-gradient)":"#c8bfd3", "url(#back-glow)":"#ffffff"}.get(colour,"#e8f0e8")
    if colour == "black": colour="#000000"
    if len(colour)==4 and colour.startswith("#"):
        colour="#"+"".join(ch*2 for ch in colour[1:])
    if not colour.startswith("#") or len(colour)!=7: return colour
    a=[int(colour[j:j+2],16) for j in (1,3,5)]
    b=[int(background[j:j+2],16) for j in (1,3,5)]
    return "#"+"".join(f"{round(v*opacity+w*(1-opacity)):02x}" for v,w in zip(a,b))


class SVGScene:
    def __init__(self, html_path: Path):
        html=html_path.read_text(encoding="utf-8")
        match=re.search(r'<svg id="anatomy"[\s\S]*?</svg>',html)
        if not match: raise ValueError("В interface.html не найдена схема anatomy.")
        self.root=ET.fromstring(match.group(0))
        self.ids={element.get("id"):element for element in self.root.iter() if element.get("id")}
        self.paths={name:Polyline(self.ids[name].get("d")) for name in
                    ("air-path-left","air-path-right","blood-loop","capillary-path","arterial-path")}
        self.air=[]; self.rbc=[]; self.exchange=[]; self.delivery=[]
        for i in range(22):
            dot=ET.SubElement(self.ids["air-particles"],"circle",r="3",stroke="#fff",**{"stroke-width":"1"})
            self.air.append(dot)
        for i in range(17):
            g=ET.SubElement(self.ids["blood-cells"],"g")
            outer=ET.SubElement(g,"ellipse",rx="6.1",ry="4.6",stroke="#fff",**{"stroke-width":".6"})
            inner=ET.SubElement(g,"ellipse",rx="2.8",ry="1.8")
            dots=[ET.SubElement(g,"circle",cx=str(x),cy=str(y),r="1.8",fill="#4aaea2",stroke="#fff",**{"stroke-width":".7"}) for x,y in [(-3.2,-3),(3.8,2.2)]]
            self.rbc.append((g,outer,inner,dots))
        for group,target,count in [("exchange-particles",self.exchange,7),("delivery-particles",self.delivery,5)]:
            for i in range(count):
                target.append(ET.SubElement(self.ids[group],"circle",r="3",fill="#50b3a4",stroke="#fff",**{"stroke-width":"1"}))

    def update(self, s: dict):
        t=s["elapsed_s"]; active=s["status"]!="idle"; q=t%5; inhale=q<2
        phase=q/2 if inhale else (q-2)/3
        ex=lung_expansion(t) if active else 0; scale=.91+ex*.15; oxygen=s["oxygen_percent"]/100
        for name,cx in [("lung-left",281),("lung-right",300)]:
            self.ids[name].set("transform",f"translate({cx} 205) scale({scale}) translate({-cx} -205)")
        self.ids["diaphragm"].set("transform",f"translate(0 {ex*8})")
        self.ids["alveolus"].set("transform",f"translate(647 147) scale({1+ex*.026}) translate(-647 -147)")
        self.ids["alveolus-air"].set("opacity",str(.2+.8*oxygen if active and oxygen>0 else 0))
        self.ids["intake-arrow"].set("opacity",str(.85 if active and inhale else .18))
        self.ids["exhale-arrow"].set("opacity",str(.8 if active and not inhale else .18))
        for i,dot in enumerate(self.air):
            p=(t*.7+i/22)%1; path=self.paths["air-path-left" if i%2==0 else "air-path-right"]
            x,y=path.at((p if inhale else 1-p)*path.length)
            dot.set("cx",str(x)); dot.set("cy",str(y))
            dot.set("fill","#4fae9f" if (i+.5)/22<oxygen else "#b6c8cc")
            dot.set("opacity",str(math.sin(math.pi*p)*max(0,math.sin(math.pi*phase))**.5*.87 if active else 0))
        loop=self.paths["blood-loop"]; cap=self.paths["capillary-path"].length
        arterial=self.paths["arterial-path"].length; speed=arterial/3
        for i,(g,outer,inner,dots) in enumerate(self.rbc):
            pos=(t*speed+i*loop.length/17)%loop.length; x,y=loop.at(pos); nx,ny=loop.at(min(loop.length,pos+1))
            angle=math.degrees(math.atan2(ny-y,nx-x)); load=t-max(0,pos-cap)/speed
            loaded=active and oxygen>0 and cap*.8<pos<cap+arterial and load>.6
            g.set("transform",f"translate({x} {y}) rotate({angle})")
            outer.set("fill","#d8816c" if loaded else "#b3a7bc")
            inner.set("fill","#e9ad9c" if loaded else "#d9ccdc")
            for dot in dots: dot.set("opacity",str(min(1,.3+oxygen*1.8) if loaded else 0))
        exchanging=active and oxygen>0 and inspired_air_rate(t-.6)>.1
        for i,dot in enumerate(self.exchange):
            p=(t*.85+i/7)%1
            dot.set("cx",str(603+i*14+math.sin(p*math.pi)*2))
            dot.set("cy",str(183+abs(i-3)*1.5+p*(45-abs(i-3)*2)))
            dot.set("opacity",str(math.sin(p*math.pi)*.92 if exchanging else 0))
        delivering=active and oxygen>0 and inspired_air_rate(t-3.6)>.1
        for i,dot in enumerate(self.delivery):
            p=(t*.8+i/5)%1
            dot.set("cx",str(655+p*(52+i*3)))
            dot.set("cy",str(403+p*(17 if i%2==0 else -6)))
            dot.set("opacity",str(math.sin(p*math.pi)*.9 if delivering else 0))
        self.ids["oxygen-delivery-glow"][0].set("opacity",str(.055 if delivering else 0))

    def draw(self, canvas, state: dict):
        self.update(state)
        canvas.delete("all")
        w=max(1,canvas.winfo_width()); h=max(1,canvas.winfo_height())
        scale=min(w/820,h/510); self.scale=scale
        matrix=(scale,0,0,scale,(w-820*scale)/2,(h-510*scale)/2)
        self._render(canvas,self.root,matrix,{"fill":"black"},1.)

    def _render(self, canvas, element, matrix, inherited, opacity):
        tag=element.tag.split("}")[-1]
        if tag in ("defs","title","desc","linearGradient","radialGradient"): return
        attrs={**inherited,**element.attrib}
        matrix=multiply(matrix,parse_transform(element.get("transform","")))
        opacity*=float(element.get("opacity","1"))
        if opacity<.006: return
        if attrs.get("fill")=="url(#back-glow)" or element.get("id")=="oxygen-delivery-glow": return
        if tag in ("svg","g"):
            inheritable={k:v for k,v in attrs.items() if k in ("fill","stroke","stroke-width","stroke-linecap","stroke-linejoin","stroke-dasharray","font-size")}
            for child in element: self._render(canvas,child,matrix,inheritable,opacity)
            return
        if tag=="use":
            reference=self.ids.get(element.get("href","").lstrip("#"))
            if reference is not None:
                virtual=ET.Element(reference.tag,{**reference.attrib,**element.attrib})
                virtual.attrib.pop("transform",None)
                self._render(canvas,virtual,matrix,inherited,opacity)
            return
        fill=blend(attrs.get("fill","black"),opacity); stroke=blend(attrs.get("stroke","none"),opacity)
        width=max(.3,float(attrs.get("stroke-width","1"))*self.scale)
        def flat(points):
            return [v for point in points for v in transform_point(matrix,*point)]
        if tag=="path":
            for points,closed in flatten_path(attrs.get("d","")):
                coords=flat(points)
                if fill and len(points)>2: canvas.create_polygon(coords,fill=fill,outline="")
                if stroke and len(points)>1:
                    options={"fill":stroke,"width":width,"capstyle":"round","joinstyle":"round"}
                    if attrs.get("stroke-dasharray"):
                        options["dash"]=tuple(max(1,round(float(n)*self.scale)) for n in attrs["stroke-dasharray"].split())
                    canvas.create_line(coords,**options)
        elif tag in ("ellipse","circle"):
            cx=float(attrs.get("cx",0)); cy=float(attrs.get("cy",0))
            rx=float(attrs.get("rx",attrs.get("r",0))); ry=float(attrs.get("ry",attrs.get("r",0)))
            points=[(cx+rx*math.cos(j*math.tau/32),cy+ry*math.sin(j*math.tau/32)) for j in range(32)]
            canvas.create_polygon(flat(points),fill=fill,outline=stroke,width=width)
        elif tag=="text":
            text="".join(element.itertext()).strip()
            if not text: return
            cls=attrs.get("class","")
            size=float(attrs.get("font-size",10)); colour=attrs.get("fill")
            if "small-label" in cls: size=10; colour="#97aaa0"
            elif "detail" in cls: size=9; colour="#9cad9f"
            elif "label" in cls: size=12; colour="#678073"
            x,y=transform_point(matrix,float(attrs.get("x",0)),float(attrs.get("y",0)))
            anchor={"middle":"s","end":"se"}.get(attrs.get("text-anchor"),"sw")
            canvas.create_text(x,y+size*self.scale*.2,text=text,anchor=anchor,
                               font=("Segoe UI",-max(7,round(size*self.scale))),
                               fill=blend(colour or "#678073",opacity))
