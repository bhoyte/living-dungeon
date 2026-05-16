"""Stress markers, epigenome drift/fade, and bounded visible pigmentation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sim.constants import (
    ABUNDANCE_ENERGY_THRESHOLD,
    EPIGENOME_DELTA_CLAMP,
    EPIGENOME_MULT_MAX,
    EPIGENOME_MULT_MIN,
    EPIGENOME_TAU_SEC,
    FAMINE_ENERGY_THRESHOLD,
    MARKER_SMOOTHING,
    PREDATION_ALARM_THRESHOLD,
    STRESS_GAIN_FAMINE,
    STRESS_GAIN_PREDATION,
    STRESS_MARKER_DECAY_PER_SEC,
    STRESS_RELIEF_ABUNDANCE,
    STRESS_RELIEF_FED,
)
from sim.organisms import Epigenome, Organism

if TYPE_CHECKING:
    from sim.world import World

EPIGENOME_FIELDS = (
    "size_mult",
    "speed_mult",
    "metabolism_mult",
    "perception_mult",
    "aggression_mult",
)

PRESSURE_DELTAS: dict[str, dict[str, float]] = {
    "starvation": {
        "speed_mult": 0.05,
        "metabolism_mult": -0.08,
        "size_mult": -0.10,
        "aggression_mult": 0.05,
    },
    "predation": {
        "speed_mult": 0.15,
        "metabolism_mult": 0.10,
        "size_mult": -0.05,
        "aggression_mult": -0.10,
    },
    "abundance": {
        "speed_mult": -0.05,
        "metabolism_mult": -0.05,
        "size_mult": 0.10,
        "aggression_mult": -0.05,
    },
}


@dataclass
class AdaptationMarkers:
    starvation: float = 0.0
    predation: float = 0.0
    abundance: float = 0.0

    def dominant_pressure(self) -> str | None:
        levels = {
            "starvation": self.starvation,
            "predation": self.predation,
            "abundance": self.abundance,
        }
        name, value = max(levels.items(), key=lambda kv: kv[1])
        if value < 0.15:
            return None
        return name

    def any_active(self) -> bool:
        return max(self.starvation, self.predation, self.abundance) >= 0.15


def _smooth(current: float, target: float) -> float:
    return current + (target - current) * MARKER_SMOOTHING


def _clamp_mult(value: float) -> float:
    return max(EPIGENOME_MULT_MIN, min(EPIGENOME_MULT_MAX, value))


def _clamp_delta(delta: float) -> float:
    return max(-EPIGENOME_DELTA_CLAMP, min(EPIGENOME_DELTA_CLAMP, delta))


def _clamp_pigment(channel: float) -> float:
    return max(0.0, min(1.0, channel))


def compute_raw_pressures(org: Organism, world: World) -> dict[str, float]:
    x, y = org.pos
    alarm = float(world.field_map.fields["alarm"][y, x])
    starvation_raw = 1.0 if org.energy < FAMINE_ENERGY_THRESHOLD else 0.0
    if org.energy < FAMINE_ENERGY_THRESHOLD + 0.1:
        starvation_raw = max(
            starvation_raw,
            (FAMINE_ENERGY_THRESHOLD + 0.1 - org.energy) / 0.1,
        )
    abundance_raw = (
        1.0
        if org.energy >= ABUNDANCE_ENERGY_THRESHOLD and org.stress < 0.25
        else 0.0
    )
    predation_raw = 0.0
    if alarm >= PREDATION_ALARM_THRESHOLD:
        predation_raw = min(1.0, alarm / max(PREDATION_ALARM_THRESHOLD, 1e-6))
    if org.stress > 0.55:
        predation_raw = max(predation_raw, min(1.0, (org.stress - 0.55) / 0.45))
    return {
        "starvation": starvation_raw,
        "predation": predation_raw,
        "abundance": abundance_raw,
    }


def update_stress_markers(org: Organism, world: World, dt: float) -> AdaptationMarkers:
    markers: AdaptationMarkers = org.extensions.setdefault("markers", AdaptationMarkers())
    if not isinstance(markers, AdaptationMarkers):
        markers = AdaptationMarkers()
        org.extensions["markers"] = markers

    raw = compute_raw_pressures(org, world)
    markers.starvation = _smooth(markers.starvation, raw["starvation"])
    markers.predation = _smooth(markers.predation, raw["predation"])
    markers.abundance = _smooth(markers.abundance, raw["abundance"])
    return markers


def update_stress_from_markers(org: Organism, markers: AdaptationMarkers, dt: float) -> None:
    if markers.starvation >= 0.4:
        org.stress = min(1.0, org.stress + STRESS_GAIN_FAMINE * dt)
    if markers.predation >= 0.4:
        org.stress = min(1.0, org.stress + STRESS_GAIN_PREDATION * dt)
    if markers.abundance >= 0.4:
        org.stress = max(0.0, org.stress - STRESS_RELIEF_ABUNDANCE * dt)
    if org.energy >= 0.55 and markers.starvation < 0.25:
        org.stress = max(0.0, org.stress - STRESS_RELIEF_FED * dt)
    if not markers.any_active():
        org.stress = max(0.0, org.stress - STRESS_MARKER_DECAY_PER_SEC * dt)


def _fade_mult_toward_neutral(value: float, dt: float) -> float:
    alpha = min(1.0, dt / EPIGENOME_TAU_SEC)
    return _clamp_mult(value + (1.0 - value) * alpha)


def _apply_pressure_to_epigenome(epi: Epigenome, pressure: str, strength: float, dt: float) -> None:
    deltas = PRESSURE_DELTAS[pressure]
    for epi_field in EPIGENOME_FIELDS:
        delta = _clamp_delta(deltas.get(epi_field, 0.0))
        current = float(getattr(epi, epi_field))
        step = delta * strength * dt
        setattr(epi, epi_field, _clamp_mult(current + step))


def _should_fade_epigenome(org: Organism, markers: AdaptationMarkers) -> bool:
    if org.energy >= ABUNDANCE_ENERGY_THRESHOLD and markers.starvation < 0.30:
        return True
    if not markers.any_active():
        return True
    if org.energy >= 0.55 and org.stress < 0.45:
        if markers.starvation < 0.35 and markers.predation < 0.35:
            return True
    return False


def update_epigenome(org: Organism, markers: AdaptationMarkers, dt: float) -> None:
    epi = org.data.epigenome
    if _should_fade_epigenome(org, markers):
        for epi_field in EPIGENOME_FIELDS:
            value = float(getattr(epi, epi_field))
            setattr(epi, epi_field, _fade_mult_toward_neutral(value, dt))
        return
    dominant = markers.dominant_pressure()
    if dominant is not None:
        strength = getattr(markers, dominant)
        _apply_pressure_to_epigenome(epi, dominant, strength, dt)


def update_visible_pigmentation(org: Organism) -> tuple[float, float, float]:
    """Derive display pigmentation from base genome + epigenome drift."""
    base = org.data.base_genome.pigmentation
    epi = org.data.epigenome
    delta_r = _clamp_delta((epi.aggression_mult - 1.0) * 0.35)
    delta_g = _clamp_delta((1.0 - epi.metabolism_mult) * 0.25)
    delta_b = _clamp_delta((epi.size_mult - 1.0) * 0.20)
    visible = (
        _clamp_pigment(base[0] + delta_r),
        _clamp_pigment(base[1] + delta_g),
        _clamp_pigment(base[2] + delta_b),
    )
    org.extensions["visible_pigmentation"] = visible
    return visible


def step_epigenome(world: World, dt: float) -> None:
    for org_id in world.organism_ids_in_tick_order:
        org = next((o for o in world.organisms if o.id == org_id), None)
        if org is None or not org.alive:
            continue
        if org.data.trophic_level == 0:
            continue
        markers = update_stress_markers(org, world, dt)
        update_stress_from_markers(org, markers, dt)
        update_epigenome(org, markers, dt)
        update_visible_pigmentation(org)


def epigenome_snapshot(org: Organism) -> dict[str, float]:
    epi = org.data.epigenome
    return {name: float(getattr(epi, name)) for name in EPIGENOME_FIELDS}
