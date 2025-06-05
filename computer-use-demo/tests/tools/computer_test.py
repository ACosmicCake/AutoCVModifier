from unittest.mock import AsyncMock, patch
import math # Added
import pytest

from computer_use_demo.tools.computer import (
    ComputerTool20241022,
    ComputerTool20250124,
    ScalingSource,
    ToolError,
    ToolResult,
)


@pytest.fixture(params=[ComputerTool20241022, ComputerTool20250124])
def computer_tool(request):
    return request.param()


@pytest.mark.asyncio
async def test_computer_tool_mouse_move(computer_tool):
    with patch.object(computer_tool, "shell", new_callable=AsyncMock) as mock_shell:
        mock_shell.return_value = ToolResult(output="Mouse moved")
        result = await computer_tool(action="mouse_move", coordinate=[100, 200])
        mock_shell.assert_called_once_with(
            f"{computer_tool.xdotool} mousemove --sync 100 200"
        )
        assert result.output == "Mouse moved"


@pytest.mark.asyncio
async def test_computer_tool_type(computer_tool):
    with (
        patch.object(computer_tool, "shell", new_callable=AsyncMock) as mock_shell,
        patch.object(
            computer_tool, "screenshot", new_callable=AsyncMock
        ) as mock_screenshot,
    ):
        mock_shell.return_value = ToolResult(output="Text typed")
        mock_screenshot.return_value = ToolResult(base64_image="base64_screenshot")
        result = await computer_tool(action="type", text="Hello, World!")
        assert mock_shell.call_count == 1
        assert "type --delay 12 -- 'Hello, World!'" in mock_shell.call_args[0][0]
        assert result.output == "Text typed"
        assert result.base64_image == "base64_screenshot"


@pytest.mark.asyncio
async def test_computer_tool_screenshot(computer_tool):
    with patch.object(
        computer_tool, "screenshot", new_callable=AsyncMock
    ) as mock_screenshot:
        mock_screenshot.return_value = ToolResult(base64_image="base64_screenshot")
        result = await computer_tool(action="screenshot")
        mock_screenshot.assert_called_once()
        assert result.base64_image == "base64_screenshot"

SCALING_TEST_CASES = [
    # orig_w, orig_h, expected_comp_w, expected_comp_h
    (1920, 1080, 1280, 720),
    (1920, 1200, 1280, 800),
    (4096, 2160, 1280, 675),
    (1024, 768, 1024, 768), # Stays XGA
    (1280, 800, 1024, 640), # WXGA gets scaled down to XGA by current logic
    (1152, 864, 1024, 768),
    (1366, 768, 1280, 719),
    (2560, 1080, 1280, 540),
    (1080, 1920, 432, 768), # Corrected expected width from 430 to 432
    (800, 600, 800, 600),
    (0, 0, 0, 0),
    (100, 0, 100, 0),
    (0, 100, 0, 100),
]

@pytest.mark.parametrize(
    "orig_w, orig_h, expected_comp_w, expected_comp_h", SCALING_TEST_CASES
)
def test_coordinate_scaling_logic(computer_tool, orig_w, orig_h, expected_comp_w, expected_comp_h):
    computer_tool._scaling_enabled = True
    computer_tool.width = orig_w
    computer_tool.height = orig_h

    # Test ScalingSource.COMPUTER
    # For COMPUTER source, the input x,y for scaling are typically the full original screen dimensions
    # to find out what the scaled screen dimensions would be.
    # Or, it could be a specific coordinate on the original screen.
    # Here, we test scaling of a point that is effectively the bottom-right of the screen.
    comp_x, comp_y = computer_tool.scale_coordinates(ScalingSource.COMPUTER, orig_w, orig_h)
    assert (comp_x, comp_y) == (expected_comp_w, expected_comp_h), f"COMPUTER scaling failed for {orig_w}x{orig_h}"

    # Test ScalingSource.API
    # API coordinates are points on the (potentially) scaled display.
    # We choose a sample point (e.g., 10,10 or middle) on this scaled display.
    # Then we transform it back to what the original screen coordinate should be.
    if expected_comp_w > 0 and expected_comp_h > 0: # Only test API scaling if scaled dimensions are valid
        # Use a point that is clearly within the scaled dimensions.
        # e.g. 1/4th of the scaled dimensions, or a fixed small point if scaled dimensions are too small.
        api_x_on_scaled = expected_comp_w // 4
        api_y_on_scaled = expected_comp_h // 4

        if expected_comp_w < 4 : api_x_on_scaled = 0 # handle very small scaled dimensions
        if expected_comp_h < 4 : api_y_on_scaled = 0


        # Calculate the expected original coordinates these API points should map to.
        # This is the reverse of what the COMPUTER scaling does to these points.
        # expected_orig_x = math.ceil(api_x_on_scaled * (orig_w / expected_comp_w))
        # expected_orig_y = math.ceil(api_y_on_scaled * (orig_h / expected_comp_h))

        expected_orig_x = 0
        if expected_comp_w > 0 : # Avoid division by zero
             expected_orig_x = math.ceil(api_x_on_scaled * orig_w / expected_comp_w)
        elif orig_w == 0: # If original width is 0, scaled is 0, so point 0 should map to 0
            expected_orig_x = 0
        # else: it's a bit undefined if expected_comp_w is 0 but orig_w is not.
        # However, current scale_coordinates logic for API returns x,y if final_scaled_w/h is 0.
        # This part of the test might need refinement based on how scale_coordinates handles final_scaled_w/h = 0 for API.
        # Based on current scale_coordinates: if final_scaled_w/h <=0, it returns x,y unscaled.
        # This means if expected_comp_w/h is 0, then (api_x_on_scaled, api_y_on_scaled) would be returned.
        # Let's adjust test logic for this.

        expected_orig_y = 0
        if expected_comp_h > 0 :
            expected_orig_y = math.ceil(api_y_on_scaled * orig_h / expected_comp_h)
        elif orig_h == 0:
            expected_orig_y = 0

        from_api_x, from_api_y = computer_tool.scale_coordinates(ScalingSource.API, api_x_on_scaled, api_y_on_scaled)

        # If scaled dimensions became 0, the scale_coordinates function returns original api_x, api_y for API source
        if expected_comp_w <= 0 or expected_comp_h <= 0:
            assert (from_api_x, from_api_y) == (api_x_on_scaled, api_y_on_scaled), \
                   f"API scaling for zero scaled dim {orig_w}x{orig_h} with API point ({api_x_on_scaled},{api_y_on_scaled}) should return point itself"
        else:
            assert (from_api_x, from_api_y) == (expected_orig_x, expected_orig_y), \
                   f"API scaling failed for {orig_w}x{orig_h} with API point ({api_x_on_scaled},{api_y_on_scaled}). Expected ({expected_orig_x},{expected_orig_y}), got ({from_api_x},{from_api_y})"

def test_scaling_disabled(computer_tool):
    computer_tool._scaling_enabled = False
    computer_tool.width = 1920
    computer_tool.height = 1080

    # Test COMPUTER source
    comp_x, comp_y = computer_tool.scale_coordinates(ScalingSource.COMPUTER, 1920, 1080)
    assert (comp_x, comp_y) == (1920, 1080)

    # Test API source
    api_x, api_y = computer_tool.scale_coordinates(ScalingSource.API, 100, 100)
    assert (api_x, api_y) == (100, 100)

@pytest.mark.asyncio
async def test_computer_tool_scaling_out_of_bounds(computer_tool):
    computer_tool._scaling_enabled = True
    computer_tool.width = 1920
    computer_tool.height = 1080

    # Test scaling from API with out of bounds coordinates
    with pytest.raises(ToolError, match="Coordinates .*, .* are out of bounds"):
        x, y = computer_tool.scale_coordinates(ScalingSource.API, 2000, 1500)


@pytest.mark.asyncio
async def test_computer_tool_invalid_action(computer_tool):
    with pytest.raises(ToolError, match="Invalid action: invalid_action"):
        await computer_tool(action="invalid_action")


@pytest.mark.asyncio
async def test_computer_tool_missing_coordinate(computer_tool):
    with pytest.raises(ToolError, match="coordinate is required for mouse_move"):
        await computer_tool(action="mouse_move")


@pytest.mark.asyncio
async def test_computer_tool_missing_text(computer_tool):
    with pytest.raises(ToolError, match="text is required for type"):
        await computer_tool(action="type")
