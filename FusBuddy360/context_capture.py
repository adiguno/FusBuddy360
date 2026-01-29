import adsk.core
import adsk.fusion
import os
import base64
from datetime import datetime
from typing import Dict, Optional


def _safe_getattr(obj, name, default=None):
    try:
        return getattr(obj, name)
    except:
        return default


def _safe_count(collection) -> int:
    try:
        return int(collection.count)
    except:
        try:
            return len(collection)
        except:
            return 0


def _selection_summary(app: adsk.core.Application) -> dict:
    try:
        product = app.activeProduct
        selection = product.selection
    except:
        return {"count": 0, "types": {}, "items": []}

    types: dict[str, int] = {}
    items: list[dict] = []

    count = 0
    try:
        count = int(selection.count)
    except:
        count = 0

    # Keep payload small: include at most 10 item stubs.
    max_items = 10
    for i in range(min(count, max_items)):
        try:
            sel_item = selection.item(i)
            ent = sel_item.entity
            obj_type = _safe_getattr(ent, "objectType", "unknown")
            name = _safe_getattr(ent, "name", None)
            types[obj_type] = types.get(obj_type, 0) + 1
            items.append({"objectType": obj_type, "name": name})
        except:
            continue

    # If more than max_items are selected, we still want type counts.
    if count > max_items:
        for i in range(max_items, count):
            try:
                sel_item = selection.item(i)
                ent = sel_item.entity
                obj_type = _safe_getattr(ent, "objectType", "unknown")
                types[obj_type] = types.get(obj_type, 0) + 1
            except:
                continue

    return {"count": count, "types": types, "items": items}


def _get_temp_dir() -> str:
    """
    Returns a temp directory for storing screenshots.
    Uses the same base directory as user config.
    """
    try:
        from . import user_config
        base_dir = user_config._base_dir()
        temp_dir = os.path.join(base_dir, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        return temp_dir
    except:
        # Fallback to system temp if user_config not available
        import tempfile
        return tempfile.gettempdir()


def capture_viewport_screenshot(width: int = 800, height: int = 600, include_base64: bool = True) -> Optional[Dict[str, str]]:
    """
    Capture the current Fusion 360 viewport as a screenshot.
    
    Args:
        width: Image width in pixels (default: 800)
        height: Image height in pixels (default: 600)
        include_base64: Whether to include base64-encoded image in return (default: True)
    
    Returns:
        Dict with "path" (file path) and optionally "base64" (base64 string), or None if capture fails.
    """
    try:
        app = adsk.core.Application.get()
        viewport = app.activeViewport
        if not viewport:
            return None
        
        # Generate unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"viewport_{timestamp}.png"
        temp_dir = _get_temp_dir()
        file_path = os.path.join(temp_dir, filename)
        
        # Save screenshot
        viewport.saveAsImageFile(file_path, width, height)
        
        # Verify file was created
        if not os.path.exists(file_path):
            return None
        
        result = {"path": file_path}
        
        # Optionally include base64 encoding
        if include_base64:
            try:
                with open(file_path, "rb") as f:
                    image_data = f.read()
                    base64_str = base64.b64encode(image_data).decode("utf-8")
                    result["base64"] = base64_str
            except Exception:
                # If base64 encoding fails, still return the path
                pass
        
        return result
        
    except Exception:
        # Silently fail - screenshot capture is optional
        return None


def capture_context() -> dict:
    """
    Capture a small, structured snapshot of the current Fusion state.
    This is intentionally read-only and intentionally small.
    """
    app = adsk.core.Application.get()
    ui = app.userInterface

    # Document
    doc_name = None
    try:
        doc = app.activeDocument
        doc_name = _safe_getattr(doc, "name", None)
    except:
        doc_name = None

    # Workspace
    workspace_id = None
    workspace_name = None
    try:
        ws = ui.activeWorkspace
        workspace_id = _safe_getattr(ws, "id", None)
        workspace_name = _safe_getattr(ws, "name", None)
    except:
        workspace_id = None
        workspace_name = None

    # Selection
    selection = _selection_summary(app)

    # Design summary (only when the active product is a Fusion Design)
    design_summary: dict = {}
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if design:
            root = design.rootComponent
            design_summary = {
                "rootComponent": _safe_getattr(root, "name", None),
                "bodies": _safe_count(root.bRepBodies),
                "sketches": _safe_count(root.sketches),
                "occurrences": _safe_count(root.occurrences),
                "components": _safe_count(design.allComponents),
            }
        else:
            design_summary = {"available": False}
    except:
        design_summary = {"available": False}

    # Viewport screenshot (included by default)
    screenshot = capture_viewport_screenshot()

    result = {
        "document": {"name": doc_name},
        "workspace": {"id": workspace_id, "name": workspace_name},
        "selection": selection,
        "design": design_summary,
    }

    if screenshot:
        result["screenshot"] = screenshot

    return result


