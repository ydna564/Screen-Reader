#!/usr/bin/env python3
"""Generate a monochrome open-book template icon for the menu bar.

Draws a simple open-book silhouette (matching the app logo) in solid black
on a transparent background, saved as a template PNG that macOS tints to
match the light/dark menu bar automatically. Run:

    ../.venv/bin/python make_menubar_icon.py
"""
import os
import AppKit

N = 44                      # retina canvas (px); shown ~20pt in the bar
OUT = os.path.join(os.path.dirname(__file__), "menubar_icon.png")


def build():
    img = AppKit.NSImage.alloc().initWithSize_((N, N))
    img.lockFocus()

    AppKit.NSColor.blackColor().set()

    def page(spine_bottom, out_bottom, out_top, spine_top):
        p = AppKit.NSBezierPath.bezierPath()
        p.moveToPoint_(spine_bottom)
        # bottom edge: gentle open-book curve rising to the outer corner
        mid = ((spine_bottom[0] + out_bottom[0]) / 2.0, out_bottom[1] - 2)
        p.curveToPoint_controlPoint1_controlPoint2_(out_bottom, mid, mid)
        p.lineToPoint_(out_top)                     # outer edge
        p.lineToPoint_(spine_top)                   # top edge to spine
        p.lineToPoint_(spine_bottom)                # spine (center)
        p.setLineWidth_(3.0)
        p.setLineJoinStyle_(AppKit.NSLineJoinStyleRound)
        p.setLineCapStyle_(AppKit.NSLineCapStyleRound)
        p.stroke()

    # left page
    page((22, 10), (6, 14), (6, 33), (22, 35))
    # right page (mirror across x=22)
    page((22, 10), (38, 14), (38, 33), (22, 35))

    img.unlockFocus()

    rep = AppKit.NSBitmapImageRep.imageRepWithData_(img.TIFFRepresentation())
    data = rep.representationUsingType_properties_(4, {})   # 4 = PNG
    data.writeToFile_atomically_(OUT, True)
    print("wrote", OUT)


if __name__ == "__main__":
    build()
