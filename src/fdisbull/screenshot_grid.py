"""Optional coordinate annotations, rendered solely from stored screenshot pixels."""
import io

from PIL import Image, ImageDraw, ImageFont


def validate_step(step):
    if type(step) is not int or not 8 <= step <= 512:
        raise ValueError('grid step must be an integer in 8..512 screenshot pixels')


def coordinate_grid(data, *, step=32, target=None):
    validate_step(step)
    with Image.open(io.BytesIO(data)) as source:
        width,height=source.size
        if not 1 <= width <= 4096 or not 1 <= height <= 4096:
            raise ValueError('Grid source dimensions must be in 1..4096 pixels')
        image=source.convert('RGBA')
    if target is not None and (not isinstance(target,(list,tuple)) or len(target)!=2
            or any(type(value) is not int for value in target)
            or not 0<=target[0]<width or not 0<=target[1]<height):
        raise ValueError('Grid target must be [x,y] inside the native screenshot')
    overlay=Image.new('RGBA',image.size)
    draw=ImageDraw.Draw(overlay)
    xs=list(range(0,width,step));ys=list(range(0,height,step))
    label_step=step*max(1,(32+step-1)//step)
    for x in xs:
        major=x%label_step==0
        if major:draw.line((x,0,x,height-1),fill=(0,0,0,100),width=3)
        draw.line((x,0,x,height-1),fill=(90,240,255,160 if major else 65),width=1)
    for y in ys:
        major=y%label_step==0
        if major:draw.line((0,y,width-1,y),fill=(0,0,0,100),width=3)
        draw.line((0,y,width-1,y),fill=(90,240,255,160 if major else 65),width=1)
    font=ImageFont.load_default(size=10)

    def label(x,y,text,colour=(180,255,255,255)):
        box=draw.textbbox((0,0),text,font=font)
        w,h=box[2]-box[0],box[3]-box[1]
        x=max(0,min(x,width-w-3));y=max(0,min(y,height-h-3))
        draw.rectangle((x,y,x+w+2,y+h+2),fill=(0,0,0,225))
        draw.text((x+1-box[0],y+1-box[1]),text,font=font,fill=colour)

    label(2,2,'0,0')
    x_labels=list(range(0,width,label_step));y_labels=list(range(0,height,label_step))
    for x in x_labels[1:]:label(x+2,2,str(x))
    for y in y_labels[1:]:label(2,y+2,str(y))
    if target is not None:
        x,y=target;colour=(255,90,180,255)
        draw.ellipse((x-4,y-4,x+4,y+4),outline=colour,width=1)
        draw.line((x-7,y,x+7,y),fill=colour,width=1)
        draw.line((x,y-7,x,y+7),fill=colour,width=1)
        label(x+9,y+8,f'{x},{y}',colour)
    result=Image.alpha_composite(image,overlay).convert('RGB')
    stream=io.BytesIO();result.save(stream,format='PNG')
    return stream.getvalue(),dict(coordinate_space='screenshot_pixels',origin=[0,0],
        max_coordinate=[width-1,height-1],step=step,x_lines=xs,y_lines=ys,
        label_step=label_step,x_labels=x_labels,y_labels=y_labels,
        target=list(target) if target is not None else None,
        x_direction='right',y_direction='down',resized=False,
        labels='x across top, y down left; native pixels, no aspect-ratio doubling')
