from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import build123d as bd
import build123d_ease as bde
from build123d_ease import show
from loguru import logger


@dataclass(frozen=True)
class PartSpec:
    """Specification for lily58_travel_case."""

    side: Literal["left", "right"]

    plane_wall_thickness: float = 2
    edge_wall_thickness: float = 2
    internal_clearance: float = 0.8  # Inset from walls (XY).

    # Total thickness of both halves of the keyboard together, with the keys
    # squished just a little bit.
    total_keyboard_thickness: float = 24.0

    magnet_od: float = 10.0 - 0.3
    magnet_height: float = 2.1

    input_pcb_cad_path: Path = (
        Path(__file__).parent / "inputs/Lily58_PCB_Edge_Only.step"
    )

    def __post_init__(self) -> None:
        """Post initialization checks."""
        assert self.input_pcb_cad_path.is_file()


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
    """Create a CAD model of lily58_travel_case.

    Nominally, the logic draws the right-half. If drawing the left-half, we
    mirror everything across the XY plane.
    """
    p = bd.Part(None)

    this_side_keyboard_thickness: float = 7  # Hack: Set lower value.

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

    wall_outline = bd.make_face(outside_outline.edges()) - bd.make_face(
        inside_outline.edges()
    )
    assert isinstance(wall_outline, bd.Compound)  # Type checking.

    # Add bottom plane wall.
    p += bd.extrude(
        outside_outline, amount=spec.plane_wall_thickness
    ).translate(
        (
            0,
            0,
            -this_side_keyboard_thickness - spec.plane_wall_thickness,
        )
    )

    # Add walls around edge of keyboard.
    p += bd.extrude(
        # Pyright: `wall_outline` is a compound, but the extrude still works.
        wall_outline,  # pyright: ignore[reportArgumentType]
        amount=this_side_keyboard_thickness,
    ).translate((0, 0, -this_side_keyboard_thickness))

    # Add magnet holder pockets to vertical wall faces.
    vertical_faces = [
        f
        for f in p.faces()
        # Nearly horizontal normal = vertical face:
        if abs(f.normal_at(0, 0).Z) < 0.1  # noqa: PLR2004
    ]
    vertical_faces.sort(key=lambda f: f.area, reverse=True)  # Largest first
    vertical_faces = [
        f
        for idx, f in enumerate(vertical_faces)
        # Manually select the 4 target faces for magnets (nth largest faces):
        if idx in (0, 1, 4, 6)
    ]

    # Add magnets to the vertical faces.
    for face in vertical_faces:
        # Boss center: same XY as face center, but at the target magnet Z.
        boss_center = face.center(bd.CenterOf.BOUNDING_BOX)

        # Build boss as a box extruded outward from the face.
        # Use a Plane so +Z of the plane = outward normal of the face.
        boss_plane = bd.Plane(
            origin=boss_center,
            x_dir=bd.Vector(0, 0, 1),  # X will be the vertical direction.
            z_dir=face.normal_at(0, 0),  # Z will point out of the face.
        )
        boss_box = bde.RoundedBox(
            # Size in Z:
            spec.plane_wall_thickness + this_side_keyboard_thickness,
            # Size along face:
            spec.magnet_od + 3.0 * 2,
            # Size normal to face:
            spec.magnet_od + 3.0 + 1.0,  # Add extra 1mm for tolerance.
            align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
            radius=3.0,
            edges="X",
        )

        magnet_hex = bd.RegularPolygon(
            radius=spec.magnet_od / 2,
            side_count=6,
            # Radius is inscribed. Flat-to-flat = magnet_od.
            major_radius=False,
        )
        box_face_with_magnet = boss_box.faces().sort_by(bd.Axis.X)[-1]
        magnet_hex_at_location = (  # pyright: ignore[reportUnknownVariableType]
            bd.Plane(
                box_face_with_magnet.center(),
                z_dir=box_face_with_magnet.normal_at(0, 0),
            )
            * magnet_hex
        )

        magnet_pocket = bd.extrude(
            magnet_hex_at_location,  # pyright: ignore[reportArgumentType]
            amount=-spec.plane_wall_thickness,  # depth into the X face
        )
        boss_box -= magnet_pocket  # Cut magnet pocket out of boss.

        boss = boss_plane * boss_box  # pyright: ignore[reportUnknownVariableType]

        assert isinstance(boss, bd.Part | bd.Compound)  # Type checking.
        p += boss

    # Remove spot on back wall for place for wire bit.
    # Note: Must come after adding magnet bosses.
    left_wall_x_pos = -71
    back_wall_y_pos = 37.8
    p -= bd.Pos(Y=back_wall_y_pos) * bd.Box(
        2 * 34.5,
        200,
        spec.total_keyboard_thickness,
        align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.CENTER),
    ).translate((left_wall_x_pos, 0, 0))

    if spec.side == "left":
        p = p.mirror(mirror_plane=bd.Plane.XY)

    return p


def render_both_halves() -> bd.Compound:
    """Render both halves of the case."""
    left_half = make_lily58_travel_case(PartSpec("left"))
    right_half = make_lily58_travel_case(PartSpec("right"))

    left_half = left_half.rotate(bd.Axis.Y, angle=180)

    # Space between the two halves.
    gap = 10

    # Flush left half so its right edge (max.X) sits at -gap
    left_offset = -gap - left_half.bounding_box().max.X
    # Flush right half so its left edge (min.X) sits at +gap
    right_offset = gap - right_half.bounding_box().min.X

    p = (
        bd.Part(None)
        + (bd.Pos(X=left_offset) * left_half)
        + (bd.Pos(X=right_offset) * right_half)
    )

    return p


if __name__ == "__main__":
    parts = {
        # "pcb_outline": show(get_pcb_outline(PartSpec().input_pcb_cad_path)),
        "lily58_travel_case_right": show(  # Best half for development/design.
            make_lily58_travel_case(PartSpec("right"))
        ),
        "lily58_travel_case_left": (make_lily58_travel_case(PartSpec("left"))),
        "both_halves": show(render_both_halves()),
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
