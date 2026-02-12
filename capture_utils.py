import os
import time
import logging

from typing import Tuple


def compute_physical_capture_region(
    nx: int, ny: int, nw: int, nh: int, widget
) -> Tuple[int, int, int, int]:
    """Map a logical inset selection (nx,ny,nw,nh) to physical pixel capture region.

    Attempts to use the Qt screen DPR and `mss` monitor origins for accurate
    physical coordinates. Returns (phys_left, phys_top, phys_w, phys_h).
    """
    try:
        from PyQt5 import QtWidgets, QtCore

        screen = QtWidgets.QApplication.screenAt(QtCore.QPoint(int(nx), int(ny)))
        if screen is None:
            screen = QtWidgets.QApplication.primaryScreen()

        try:
            dpr = (
                float(screen.devicePixelRatioF())
                if hasattr(screen, "devicePixelRatioF")
                else float(screen.devicePixelRatio())
            )
        except Exception:
            try:
                dpr = float(
                    widget.devicePixelRatioF()
                    if hasattr(widget, "devicePixelRatioF")
                    else 1.0
                )
            except Exception:
                dpr = 1.0

        sgeom = screen.geometry()
        logical_origin_x = sgeom.x()
        logical_origin_y = sgeom.y()

        phys_origin_x = int(round(logical_origin_x))
        phys_origin_y = int(round(logical_origin_y))
        scaled_origin_x = int(round(logical_origin_x * dpr))
        scaled_origin_y = int(round(logical_origin_y * dpr))

        try:
            import mss as _mss

            mons = _mss.mss().monitors
            matched = None
            for m in mons[1:]:
                try:
                    m_left = int(m.get("left", 0))
                    m_top = int(m.get("top", 0))
                except Exception:
                    continue
                if abs(m_left - phys_origin_x) < 4 and abs(m_top - phys_origin_y) < 4:
                    matched = m
                    break
                if (
                    abs(m_left - scaled_origin_x) < 4
                    and abs(m_top - scaled_origin_y) < 4
                ):
                    matched = m
                    break
            if matched:
                phys_origin_x = int(matched.get("left", phys_origin_x))
                phys_origin_y = int(matched.get("top", phys_origin_y))
        except Exception:
            pass

        phys_left = phys_origin_x + int(round((nx - logical_origin_x) * dpr))
        phys_top = phys_origin_y + int(round((ny - logical_origin_y) * dpr))
        phys_w = int(round(nw * dpr))
        phys_h = int(round(nh * dpr))
    except Exception:
        # Fallback: scale by widget DPR
        try:
            dpr = float(
                widget.devicePixelRatioF()
                if hasattr(widget, "devicePixelRatioF")
                else 1.0
            )
        except Exception:
            dpr = 1.0
        phys_left = int(round(nx * dpr))
        phys_top = int(round(ny * dpr))
        phys_w = int(round(nw * dpr))
        phys_h = int(round(nh * dpr))

    # write overlay->capture mapping debug info
    try:
        dbgdir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(dbgdir, exist_ok=True)
        dbgfile = os.path.join(dbgdir, "capture_overlay_debug.txt")
        with open(dbgfile, "a", encoding="utf-8") as f:
            ts = time.time()
            f.write(f"time: {ts}\n")
            try:
                f.write(f"inset_sel: {(nx, ny, nw, nh)}\n")
            except Exception:
                pass
            try:
                sgeom = screen.geometry()
                geom_str = "{},{},{},{}".format(
                    sgeom.x(), sgeom.y(), sgeom.width(), sgeom.height()
                )
                f.write("screen_geom: " + geom_str + "\n")
            except Exception:
                f.write("screen_geom: <error>\n")
            f.write("dpr: " + str(dpr) + "\n")
            try:
                phys_origin_str = ",".join([str(phys_origin_x), str(phys_origin_y)])
                f.write("phys_origin: " + phys_origin_str + "\n")
                phys_rect_str = ",".join(
                    [str(phys_left), str(phys_top), str(phys_w), str(phys_h)]
                )
                f.write("phys_rect: " + phys_rect_str + "\n")
            except Exception:
                f.write("phys: <error>\n")
            f.write("\n")
    except Exception:
        logging.exception("Failed to write capture debug info")

    # Clamp to virtual desktop physical bounds if mss available
    try:
        import mss as _mss

        v = _mss.mss().monitors[0]
        vleft = int(v.get("left", 0))
        vtop = int(v.get("top", 0))
        vright = vleft + int(v.get("width", 0))
        vbottom = vtop + int(v.get("height", 0))
        if phys_left < vleft:
            phys_left = vleft
        if phys_top < vtop:
            phys_top = vtop
        if phys_left + phys_w > vright:
            phys_left = max(vleft, vright - phys_w)
        if phys_top + phys_h > vbottom:
            phys_top = max(vtop, vbottom - phys_h)
    except Exception:
        pass

    return (phys_left, phys_top, phys_w, phys_h)
