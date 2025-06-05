import asyncio
import base64
import math
import os
import platform # Added
import shlex
import shutil
from PIL import Image, ImageGrab # Added
import pyautogui # Added: New dependency for GUI automation
from strenum import StrEnum # Changed for Python 3.10 compatibility
from pathlib import Path
from typing import Literal, TypedDict, cast, get_args
from uuid import uuid4

from anthropic.types.beta import BetaToolComputerUse20241022Param, BetaToolUnionParam

from .base import BaseAnthropicTool, ToolError, ToolResult
from .run import run

VALID_MODIFIER_KEYS = {'alt', 'ctrl', 'shift', 'cmd', 'command', 'option', 'win',
                           'control', 'left_shift', 'right_shift', 'left_alt', 'right_alt',
                           'left_ctrl', 'right_ctrl', 'left_cmd', 'right_cmd',
                           'left_command', 'right_command', 'left_win', 'right_win', 'windows'}

OUTPUT_DIR = "/tmp/outputs"

TYPING_DELAY_MS = 12
TYPING_GROUP_SIZE = 50

Action_20241022 = Literal[
    "key",
    "type",
    "mouse_move",
    "left_click",
    "left_click_drag",
    "right_click",
    "middle_click",
    "double_click",
    "screenshot",
    "cursor_position",
]

Action_20250124 = (
    Action_20241022
    | Literal[
        "left_mouse_down",
        "left_mouse_up",
        "scroll",
        "hold_key",
        "wait",
        "triple_click",
    ]
)

ScrollDirection = Literal["up", "down", "left", "right"]


class Resolution(TypedDict):
    width: int
    height: int


# sizes above XGA/WXGA are not recommended (see README.md)
# scale down to one of these targets if ComputerTool._scaling_enabled is set
MAX_SCALING_TARGETS: dict[str, Resolution] = {
    "XGA": Resolution(width=1024, height=768),  # 4:3
    "WXGA": Resolution(width=1280, height=800),  # 16:10
    "FWXGA": Resolution(width=1366, height=768),  # ~16:9
}

CLICK_BUTTONS = {
    "left_click": 1,
    "right_click": 3,
    "middle_click": 2,
    "double_click": "--repeat 2 --delay 10 1",
    "triple_click": "--repeat 3 --delay 10 1",
}


class ScalingSource(StrEnum):
    COMPUTER = "computer"
    API = "api"


class ComputerToolOptions(TypedDict):
    display_height_px: int
    display_width_px: int
    display_number: int | None


def chunks(s: str, chunk_size: int) -> list[str]:
    return [s[i : i + chunk_size] for i in range(0, len(s), chunk_size)]


class BaseComputerTool:
    """
    A tool that allows the agent to interact with the screen, keyboard, and mouse of the current computer.
    The tool parameters are defined by Anthropic and are not editable.
    """

    name: Literal["computer"] = "computer"
    width: int
    height: int
    display_num: int | None

    _screenshot_delay = 2.0
    _scaling_enabled = True

    @property
    def options(self) -> ComputerToolOptions:
        width, height = self.scale_coordinates(
            ScalingSource.COMPUTER, self.width, self.height
        )
        return {
            "display_width_px": width,
            "display_height_px": height,
            "display_number": self.display_num,
        }

    def __init__(self):
        super().__init__()

        # Attempt to use pyautogui for screen dimensions
        try:
            self.width, self.height = pyautogui.size()
        except Exception as e: # Broad exception to catch pyautogui issues (e.g. headless environment)
            print(f"Warning: PyAutoGUI failed to get screen size ({e}), falling back to environment variables.")
            self.width = int(os.getenv("WIDTH") or 0)
            self.height = int(os.getenv("HEIGHT") or 0)

        if not self.width or not self.height:
             # Fallback if environment variables also don't provide dimensions
            print("Warning: Screen dimensions are not accurately determined. GUI operations might be affected.")
            # Set to a common default or raise an error, depending on desired strictness
            # For now, let's keep the assert but it might need adjustment based on how often this occurs
            self.width = self.width or 1920 # Default width if 0
            self.height = self.height or 1080 # Default height if 0

        assert self.width and self.height, "Screen width and height must be determined."

        if (display_num := os.getenv("DISPLAY_NUM")) is not None:
            self.display_num = int(display_num)
        else:
            self.display_num = None

    async def __call__(
        self,
        *,
        action: Action_20241022,
        text: str | None = None,
        coordinate: tuple[int, int] | None = None,
        **kwargs, # key argument might be passed here from ComputerTool20250124
    ):
        key_modifier = kwargs.get("key") if kwargs else None # For actions like click with modifier

        try:
            if action == "mouse_move":
                if coordinate is None: raise ToolError(f"coordinate is required for {action}")
                if text is not None: raise ToolError(f"text is not accepted for {action}")
                x, y = self.validate_and_get_coordinates(coordinate)
                pyautogui.moveTo(x, y)
                return await self.screenshot()

            elif action == "left_click_drag":
                if coordinate is None: raise ToolError(f"coordinate is required for {action}")
                if text is not None: raise ToolError(f"text is not accepted for {action}")
                x, y = self.validate_and_get_coordinates(coordinate)
                # Assuming current mouse position is the start of the drag
                pyautogui.dragTo(x, y, button='left')
                return await self.screenshot()

            elif action == "key":
                if text is None: raise ToolError(f"text is required for {action}")
                if coordinate is not None: raise ToolError(f"coordinate is not accepted for {action}")
                if not isinstance(text, str): raise ToolError(output=f"{text} must be a string")
                # pyautogui.press expects single keys, or a list of keys for combinations
                # For complex key sequences like 'ctrl+shift+esc', text might need parsing if xdotool handled it.
                # For now, assuming 'text' is a single key or a sequence pyautogui.typewrite can handle as individual presses.
                # If 'text' is like 'ctrl+c', it should be pyautogui.hotkey('ctrl', 'c')
                # If 'text' is a single special key like 'enter', pyautogui.press('enter')
                # This part might need more sophisticated parsing of 'text' if it contains modifiers.
                # For now, using pyautogui.typewrite for general keys and press for special ones if distinguishable.
                # A simple approach: if it's a known special key, use press, otherwise typewrite.
                # Or, more robustly, parse 'text' for modifiers.
                # Let's assume 'text' is a key name pyautogui.press understands or a sequence for typewrite.
                # Given xdotool's `key -- <text>`, it implies pressing a combination or sequence.
                # pyautogui.hotkey is better for combinations. Let's assume simple keys for now.
                # If text involves combinations like "ctrl+alt+delete", this needs to be parsed to pyautogui.hotkey('ctrl', 'alt', 'delete')
                # For single keys like "enter", "shift", "a", "F1", pyautogui.press(text) is fine.
                # Let's assume 'text' is a single key name for now, or a sequence of characters.
                # If it's a longer string, it should be 'type' action.
                # 'key' action in xdotool implies a single key press event (possibly with modifiers).
                # A simple solution for now:
                pyautogui.press(text.split('+')) # Handles 'a', 'enter', and also 'ctrl+c' -> ['ctrl', 'c']
                return await self.screenshot()

            elif action == "type":
                if text is None: raise ToolError(f"text is required for {action}")
                if coordinate is not None: raise ToolError(f"coordinate is not accepted for {action}")
                if not isinstance(text, str): raise ToolError(output=f"{text} must be a string")
                typing_interval = TYPING_DELAY_MS / 1000.0
                # PyAutoGUI's typewrite is good for strings.
                # xdotool's 'type' also had a delay.
                pyautogui.write(text, interval=typing_interval)
                return await self.screenshot()

            elif action == "screenshot":
                if text is not None: raise ToolError(f"text is not accepted for {action}")
                if coordinate is not None: raise ToolError(f"coordinate is not accepted for {action}")
                return await self.screenshot() # Already updated to use Pillow

            elif action == "cursor_position":
                if text is not None: raise ToolError(f"text is not accepted for {action}")
                if coordinate is not None: raise ToolError(f"coordinate is not accepted for {action}")
                x_orig, y_orig = pyautogui.position()
                # Scale to API coordinates if scaling is enabled
                x_scaled, y_scaled = self.scale_coordinates(ScalingSource.COMPUTER, x_orig, y_orig)
                return ToolResult(output=f"X={x_scaled},Y={y_scaled}") # No screenshot needed

            elif action in ("left_click", "right_click", "middle_click", "double_click"):
                if text is not None: raise ToolError(f"text is not accepted for {action}")
                # coordinate is optional for clicks; if provided, move first.
                if coordinate is not None:
                    x, y = self.validate_and_get_coordinates(coordinate)
                    pyautogui.moveTo(x, y)

                click_button_map = {
                    "left_click": "left",
                    "right_click": "right",
                    "middle_click": "middle",
                }

                pyautogui_action = None
                if action == "double_click":
                    pyautogui_action = lambda: pyautogui.doubleClick(button='left')
                elif action == "triple_click": # Though triple_click is in 20250124, good to have base
                     pyautogui_action = lambda: pyautogui.tripleClick(button='left')
                else: # single clicks
                    pyautogui_action = lambda: pyautogui.click(button=click_button_map[action])

                if key_modifier: # Passed from ComputerTool20250124 for click with modifier
                    pyautogui.keyDown(key_modifier)
                    pyautogui_action()
                    pyautogui.keyUp(key_modifier)
                else:
                    pyautogui_action()
                return await self.screenshot()

            else:
                raise ToolError(f"Invalid or unhandled action in BaseComputerTool: {action}")

        except ImportError:
            raise ToolError("PyAutoGUI is required for GUI automation but not installed.")
        except pyautogui.FailSafeException:
            raise ToolError("PyAutoGUI FailSafeException: Mouse moved to a corner (0,0 typically). Action aborted.")
        except Exception as e:
            raise ToolError(f"Error during GUI action '{action}': {e}")

    def validate_and_get_coordinates(self, coordinate: tuple[int, int] | None = None):
        if not isinstance(coordinate, list) or len(coordinate) != 2:
            raise ToolError(f"{coordinate} must be a tuple of length 2")
        if not all(isinstance(i, int) and i >= 0 for i in coordinate):
            raise ToolError(f"{coordinate} must be a tuple of non-negative ints")

        return self.scale_coordinates(ScalingSource.API, coordinate[0], coordinate[1])

    async def screenshot(self):
        """Take a screenshot of the current screen and return the base64 encoded image."""
        output_dir = Path(OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"screenshot_{uuid4().hex}.png"
        error_message = None

        try:
            # Use Pillow ImageGrab for cross-platform screenshot
            img = ImageGrab.grab()

            if self._scaling_enabled:
                scaled_width, scaled_height = self.scale_coordinates(
                    ScalingSource.COMPUTER, self.width, self.height
                )
                # Ensure dimensions are integers for resize
                img = img.resize((int(scaled_width), int(scaled_height)), Image.Resampling.LANCZOS)

            img.save(path, "PNG")

            if path.exists():
                return ToolResult(base64_image=base64.b64encode(path.read_bytes()).decode())
            else:
                error_message = "Screenshot file was not saved correctly."
        except ImportError:
            raise ToolError("Pillow (PIL) is required for screenshots but not installed.")
        except Exception as e: # Catch other ImageGrab or Pillow errors
            error_message = f"Failed to take screenshot using Pillow/ImageGrab: {e}"

        # Fallback or error reporting if Pillow fails
        # For now, we raise a ToolError if Pillow method fails.
        # Original gnome-screenshot/scrot logic could be a fallback for Linux here if desired.
        if error_message:
            raise ToolError(error_message)

        # This part should ideally not be reached if Pillow is the primary method
        # and an error is raised on its failure.
        # If a fallback to shell commands for screenshots is desired for Linux, that logic would go here.
        # For now, assuming Pillow is the way.
        raise ToolError("Screenshot failed and no fallback mechanism is implemented.")


    async def shell(self, command: str, take_screenshot=True) -> ToolResult:
        """Run a shell command and return the output, error, and optionally a screenshot."""
        _, stdout, stderr = await run(command)
        base64_image = None

        if take_screenshot:
            # delay to let things settle before taking a screenshot
            await asyncio.sleep(self._screenshot_delay)
            base64_image = (await self.screenshot()).base64_image

        return ToolResult(output=stdout, error=stderr, base64_image=base64_image)

    def scale_coordinates(self, source: ScalingSource, x: int, y: int):
        if not self._scaling_enabled:
            return x, y

        current_w, current_h = self.width, self.height
        if current_w <= 0 or current_h <= 0:
            return x, y

        original_aspect_ratio = current_w / current_h

        # Ensure MAX_SCALING_TARGETS is defined in the scope and has these keys
        xga_spec = MAX_SCALING_TARGETS["XGA"]
        wxga_spec = MAX_SCALING_TARGETS["WXGA"]

        target_bound_w = current_w
        target_bound_h = current_h
        must_scale = False

        if current_w > wxga_spec["width"] or current_h > wxga_spec["height"]:
            xga_aspect = xga_spec["width"] / xga_spec["height"]
            wxga_aspect = wxga_spec["width"] / wxga_spec["height"]

            diff_xga = abs(original_aspect_ratio - xga_aspect)
            diff_wxga = abs(original_aspect_ratio - wxga_aspect)

            if diff_wxga <= diff_xga:
                target_bound_w, target_bound_h = wxga_spec["width"], wxga_spec["height"]
            else:
                target_bound_w, target_bound_h = xga_spec["width"], xga_spec["height"]
            must_scale = True

        elif current_w > xga_spec["width"] or current_h > xga_spec["height"]:
            target_bound_w, target_bound_h = xga_spec["width"], xga_spec["height"]
            must_scale = True

        else:
            return x, y

        if not must_scale:
            return x,y

        scaled_w = target_bound_w
        scaled_h = int(target_bound_w / original_aspect_ratio) if original_aspect_ratio != 0 else target_bound_h

        if scaled_h > target_bound_h:
            scaled_h = target_bound_h
            scaled_w = int(target_bound_h * original_aspect_ratio)

        final_scaled_w = min(scaled_w, target_bound_w)
        final_scaled_h = min(scaled_h, target_bound_h)

        if final_scaled_w < 1 and target_bound_w >=1 : final_scaled_w = 1
        if final_scaled_h < 1 and target_bound_h >=1 : final_scaled_h = 1

        if source == ScalingSource.API:
            if x > final_scaled_w or y > final_scaled_h:
                raise ToolError(f"Coordinates {x}, {y} are out of bounds for scaled display {final_scaled_w}x{final_scaled_h}")

            if final_scaled_w <= 0 or final_scaled_h <= 0:
                return x, y

            x_scale_factor = current_w / final_scaled_w
            y_scale_factor = current_h / final_scaled_h

            return math.ceil(x * x_scale_factor), math.ceil(y * y_scale_factor)

        else: # ScalingSource.COMPUTER
            if current_w <= 0 or current_h <= 0:
                return x,y

            # If final_scaled_w or final_scaled_h is zero, scaling factor calculation would lead to error or incorrect values.
            # This can happen if original_aspect_ratio is extreme or zero, leading to one scaled dim being zero.
            if final_scaled_w <= 0 or final_scaled_h <= 0 : # effectively means no valid scaled image
                 # In this case, perhaps return unscaled coordinates or a defined error/default.
                 # For now, returning unscaled if scaled dimensions are not positive.
                return x,y


            x_scale_factor = final_scaled_w / current_w
            y_scale_factor = final_scaled_h / current_h

            return math.floor(x * x_scale_factor), math.floor(y * y_scale_factor)


class ComputerTool20241022(BaseComputerTool, BaseAnthropicTool):
    api_type: Literal["computer_20241022"] = "computer_20241022"

    def to_params(self) -> BetaToolComputerUse20241022Param:
        return {"name": self.name, "type": self.api_type, **self.options}


class ComputerTool20250124(BaseComputerTool, BaseAnthropicTool):
    api_type: Literal["computer_20250124"] = "computer_20250124"

    def to_params(self):
        return cast(
            BetaToolUnionParam,
            {"name": self.name, "type": self.api_type, **self.options},
        )

    async def __call__(
        self,
        *,
        action: Action_20250124,
        text: str | None = None,
        coordinate: tuple[int, int] | None = None,
        scroll_direction: ScrollDirection | None = None,
        scroll_amount: int | None = None,
        duration: int | float | None = None,
        key: str | None = None,
        **kwargs,
    ):
        validated_key = None
        if key is not None:
            processed_key = key.lower() # Process once
            if processed_key in VALID_MODIFIER_KEYS:
                validated_key = processed_key
            else:
                # Optional: print(f"Warning: Invalid modifier key '{key}' provided. Ignoring.")
                pass # validated_key remains None

        try:
            if action == "left_mouse_down":
                if coordinate is not None: # xdotool allowed this, but pyautogui.mouseDown does not take coords. Move first.
                    x, y = self.validate_and_get_coordinates(coordinate)
                    pyautogui.moveTo(x, y)
                pyautogui.mouseDown(button='left')
                return await self.screenshot()

            elif action == "left_mouse_up":
                if coordinate is not None: # xdotool allowed this, but pyautogui.mouseUp does not take coords. Move first.
                    x, y = self.validate_and_get_coordinates(coordinate)
                    pyautogui.moveTo(x, y)
                pyautogui.mouseUp(button='left')
                return await self.screenshot()

            elif action == "scroll":
                if scroll_direction is None or scroll_direction not in get_args(ScrollDirection):
                    raise ToolError(f"{scroll_direction=} must be 'up', 'down', 'left', or 'right'")
                if not isinstance(scroll_amount, int) or scroll_amount <= 0: # scroll_amount should be positive
                    raise ToolError(f"{scroll_amount=} must be a positive int")

                if coordinate is not None:
                    x, y = self.validate_and_get_coordinates(coordinate)
                    pyautogui.moveTo(x, y)

                # pyautogui.scroll takes positive for up/right, negative for down/left
                scroll_val = 0
                if scroll_direction == "up":
                    scroll_val = scroll_amount
                elif scroll_direction == "down":
                    scroll_val = -scroll_amount
                elif scroll_direction == "left": # Horizontal scroll
                    # PyAutoGUI's main scroll is vertical. hscroll for horizontal.
                    pyautogui.hscroll(-scroll_amount) # Negative for left
                    return await self.screenshot()
                elif scroll_direction == "right": # Horizontal scroll
                    pyautogui.hscroll(scroll_amount)  # Positive for right
                    return await self.screenshot()

                if validated_key: # Modifier for scroll, e.g. Ctrl+scroll to zoom
                    pyautogui.keyDown(validated_key)
                pyautogui.scroll(scroll_val)
                if validated_key:
                    pyautogui.keyUp(validated_key)
                return await self.screenshot()

            elif action == "hold_key":
                if duration is None or not isinstance(duration, (int, float)) or duration < 0:
                    raise ToolError(f"{duration=} must be a non-negative number")
                if duration > 100: raise ToolError(f"{duration=} is too long.")
                if text is None: raise ToolError(f"text (key to hold) is required for {action}")

                pyautogui.keyDown(text)
                await asyncio.sleep(duration)
                pyautogui.keyUp(text)
                return await self.screenshot()

            elif action == "wait":
                if duration is None or not isinstance(duration, (int, float)) or duration < 0:
                    raise ToolError(f"{duration=} must be a non-negative number")
                if duration > 100: raise ToolError(f"{duration=} is too long.")
                await asyncio.sleep(duration)
                return await self.screenshot() # Screenshot after waiting

            elif action == "triple_click":
                if text is not None: raise ToolError(f"text is not accepted for {action}")
                if coordinate is not None:
                    x, y = self.validate_and_get_coordinates(coordinate)
                    pyautogui.moveTo(x, y)
                if validated_key:
                    pyautogui.keyDown(validated_key)
                pyautogui.tripleClick(button='left') # PyAutoGUI has tripleClick
                if validated_key:
                    pyautogui.keyUp(validated_key)
                return await self.screenshot()

            # For other click actions (left_click, right_click, etc.),
            # they are handled by BaseComputerTool.__call__, but we need to pass `key` if present.
            elif action in ("left_click", "right_click", "double_click", "middle_click"):
                 # The base class __call__ is already set up to look for 'key' in kwargs
                return await super().__call__(action=action, text=text, coordinate=coordinate, key=validated_key, **kwargs)

            # Fallback to base class for actions not specifically handled here but are part of Action_20250124
            # (e.g., basic key, type, mouse_move, screenshot, cursor_position if they were not overridden)
            else:
                return await super().__call__(action=action, text=text, coordinate=coordinate, key=validated_key, **kwargs)

        except ImportError:
            raise ToolError("PyAutoGUI is required for GUI automation but not installed.")
        except pyautogui.FailSafeException:
            raise ToolError("PyAutoGUI FailSafeException: Mouse moved to a corner (0,0 typically). Action aborted.")
        except Exception as e:
            raise ToolError(f"Error during GUI action '{action}' in ComputerTool20250124: {e}")
