"""Pure hit testing and validation for the authenticated phone control protocol."""
import json
import math


def control_allowed(authenticated, capable, enabled):
    return authenticated is True and capable is True and enabled is True


def image_point(x, y, widget_w, widget_h, image_w, image_h):
    """Map a pixel in a centered rendered image; black bars never hit.

    Dimensions describe the actual PhotoImage, not the original video frame.
    The first and last image pixels map exactly to normalized 0 and 1.
    """
    values = (x, y, widget_w, widget_h, image_w, image_h)
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        return None
    if min(widget_w, widget_h, image_w, image_h) <= 0:
        return None
    if image_w > widget_w or image_h > widget_h:
        return None
    left = (widget_w - image_w) // 2
    top = (widget_h - image_h) // 2
    if not (left <= x < left + image_w and top <= y < top + image_h):
        return None
    return (min(1.0, (x - left) / max(1, image_w - 1)),
            min(1.0, (y - top) / max(1, image_h - 1)))


def gesture_command(start, end, elapsed, distance):
    """One atomic command on release; 8px slop and 550ms long press."""
    result = {"action": "tap", "x": start[0], "y": start[1]}
    if distance >= 8:
        result.update(action="swipe", x2=end[0], y2=end[1],
                      duration=max(50, min(2000, int(elapsed * 1000))))
    elif elapsed >= 0.55:
        result["action"] = "longpress"
    return result


def encode_control(command):
    """Validate the exact wire schema and enforce both character/byte limits."""
    if not isinstance(command, dict):
        raise ValueError("control must be an object")
    action = command.get("action")
    fields = {"tap": {"action", "x", "y"},
              "longpress": {"action", "x", "y"},
              "swipe": {"action", "x", "y", "x2", "y2", "duration"},
              "global": {"action", "name"}, "text": {"action", "text"}}
    if not isinstance(action, str) or action not in fields or set(command) != fields[action]:
        raise ValueError("unknown action or invalid fields")
    for key in ("x", "y", "x2", "y2"):
        if key in command:
            v = command[key]
            if type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1:
                raise ValueError("coordinates must be finite normalized numbers")
    if action == "swipe":
        duration = command["duration"]
        if type(duration) is not int or not 50 <= duration <= 2000:
            raise ValueError("swipe duration must be 50..2000ms")
    if action == "global" and command["name"] not in ("back", "home", "recents", "notifications"):
        raise ValueError("unknown global action")
    if action == "text" and (not isinstance(command["text"], str) or len(command["text"]) > 2000):
        raise ValueError("text must contain at most 2000 characters")
    try:
        payload = json.dumps(command, ensure_ascii=False, allow_nan=False,
                             separators=(",", ":")).encode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise ValueError("invalid control encoding") from exc
    if len(payload) > 8192:
        raise ValueError("control payload exceeds 8192 bytes")
    return payload
