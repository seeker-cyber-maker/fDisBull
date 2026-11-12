"""Bounded native-pixel action regions, shared by rendering and input checks."""
from PIL import Image, ImageChops, ImageDraw


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'Scene integer must be in {low}..{high}')
    return value


def dimensions(width, height):
    integer(width, 1, 4096); integer(height, 1, 4096)
    if width * height > 1048576:
        raise ValueError('Scene exceeds one million native pixels')


def region(shape, width, height):
    """Rectangles use half-open bounds; polygon raster edges are included.

    Boolean composition operates on the resulting binary native-pixel masks.
    There is deliberately no Python/equation evaluation or SVG execution.
    """
    dimensions(width, height)
    nodes = 0

    def draw(item, depth=0):
        nonlocal nodes
        nodes += 1
        if depth > 8 or nodes > 128 or not isinstance(item, dict) or len(item) != 1:
            raise ValueError('Invalid or excessive scene geometry')
        op, data = next(iter(item.items()))
        mask = Image.new('L', (width, height))
        pen = ImageDraw.Draw(mask)
        if op == 'rect':
            if not isinstance(data, list) or len(data) != 4:
                raise ValueError('rect requires [left,top,right,bottom]')
            x0, y0, x1, y1 = data
            for x in (x0, x1): integer(x, 0, width)
            for y in (y0, y1): integer(y, 0, height)
            if x0 >= x1 or y0 >= y1:
                raise ValueError('Empty or reversed scene rectangle')
            pen.rectangle((x0, y0, x1-1, y1-1), fill=255)
            return mask
        if op == 'polygon':
            if not isinstance(data, list) or not 3 <= len(data) <= 256:
                raise ValueError('polygon requires 3..256 native points')
            for p in data:
                if not isinstance(p, list) or len(p) != 2:
                    raise ValueError('Invalid polygon point')
                integer(p[0], 0, width-1); integer(p[1], 0, height-1)
            pen.polygon([tuple(p) for p in data], fill=255)
            return mask
        if op not in ('union', 'intersection', 'subtract') or not isinstance(data, list):
            raise ValueError('Unknown scene geometry operation')
        if not 2 <= len(data) <= 64 or (op == 'subtract' and len(data) != 2):
            raise ValueError('Invalid scene geometry operands')
        mask = draw(data[0], depth+1)
        for operand in data[1:]:
            other = draw(operand, depth+1)
            mask = {'union': ImageChops.lighter, 'intersection': ImageChops.darker,
                    'subtract': ImageChops.subtract}[op](mask, other)
        return mask

    result = draw(shape)
    if result.getbbox() is None:
        raise ValueError('Scene action region is empty')
    return result
