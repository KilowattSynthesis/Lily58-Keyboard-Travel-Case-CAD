from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import build123d as bd
from build123d_ease import show  # pyright: ignore[reportMissingTypeStubs]
from loguru import logger


@dataclass(frozen=True)
class PartSpec:
    """Specification for lily58_travel_case."""

    side: Literal["left", "right"]

    plane_wall_thickness: float = 2
    edge_wall_thickness: float = 2
    internal_clearance: float = 0.8  # Inset from walls (XY).

    # Total thickness of both halves of the keyboard together.
    total_keyboard_thickness: float = 34.0

    left_edge_lip_height: float = 2

    input_pcb_cad_path: Path = (
        Path(__file__).parent / "inputs/Lily58_PCB_Edge_Only.step"
    )

    def __post_init__(self) -> None:
        """Post initialization checks."""
        assert self.input_pcb_cad_path.is_file()

    @property
    def total_height_z(self) -> float:
        """Total height of both sides of the enclosure in Z."""
        return self.plane_wall_thickness * 2 + self.total_keyboard_thickness


def _get_pcb_outline(step_path: Path) -> bd.Curve:
    """Load the PCB outline."""
    model = bd.Part(None) + bd.import_step(step_path)  # pyright: ignore[reportUnknownMemberType]

    outline = bd.project(model.wires(), workplane=bd.Plane.XY)

    assert isinstance(outline, bd.Curve)  # Type checking.

    outline = outline.translate(
        (
            -outline.bounding_box().center().X,
            -outline.bounding_box().center().Y,
        ),
    )

    return outline


def make_lily58_travel_case(
    spec: PartSpec,
) -> bd.Part | bd.Compound:
    """Create a CAD model of lily58_travel_case."""
    p = bd.Part(None)

    pcb_outline = _get_pcb_outline(spec.input_pcb_cad_path)

    pcb_outline_edges = bd.make_face(
        bd.trace(
            pcb_outline.edges(),
            line_width=0.01,
        ).edges()
    )

    inside_outline = bd.offset(
        pcb_outline_edges, amount=spec.internal_clearance
    )
    assert isinstance(inside_outline, bd.Sketch)  # Type checking.
    outside_outline = bd.offset(
        pcb_outline_edges,
        amount=(spec.internal_clearance + spec.edge_wall_thickness),
    )
    assert isinstance(outside_outline, bd.Sketch)  # Type checking.

    p += bd.extrude(
        outside_outline,
        amount=spec.plane_wall_thickness * 2 + spec.total_keyboard_thickness,
    ).translate(
        (0, 0, -spec.total_keyboard_thickness / 2 - spec.plane_wall_thickness)
    ) - bd.extrude(
        inside_outline,
        amount=spec.total_keyboard_thickness,
    ).translate((0, 0, -spec.total_keyboard_thickness / 2))

    left_wall_x_pos = -71
    back_wall_y_pos = 50

    # Remove spot on back wall for place for wire bit.
    p -= bd.Pos(Y=back_wall_y_pos) * bd.Box(
        2 * 15,
        200,
        spec.total_keyboard_thickness - 2 * spec.left_edge_lip_height,
        align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.CENTER),
    ).translate((left_wall_x_pos, 0, 0))

    return p


if __name__ == "__main__":
    parts = {
        # "pcb_outline": show(get_pcb_outline(PartSpec().input_pcb_cad_path)),
        "lily58_travel_case_left": show(
            make_lily58_travel_case(PartSpec("left"))
        ),
        "lily58_travel_case_right": (
            make_lily58_travel_case(PartSpec("right"))
        ),
    }

    logger.info("Showing CAD model(s)")

    (export_folder := Path(__file__).parent.with_name("build")).mkdir(
        exist_ok=True
    )
    for name, part in parts.items():
        assert isinstance(part, bd.Part | bd.Solid | bd.Compound), (
            f"{name} is not an expected type ({type(part)})"
        )
        if not part.is_manifold:
            logger.warning(f"Part '{name}' is not manifold")

        bd.export_stl(part, str(export_folder / f"{name}.stl"))  # pyright: ignore[reportUnknownMemberType]
        bd.export_step(part, str(export_folder / f"{name}.step"))  # pyright: ignore[reportUnknownMemberType]

    logger.info("Done saving all.")
