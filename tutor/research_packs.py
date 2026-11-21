"""Reading-to-Write 3-Source Research Packs (Ontario Strand C Comprehension + D1.3 Research + D2.1 Expository).

Turns strong reading into multi-source synthesis, inference, fact evaluation, and structured
informational paragraph writing—respecting an intelligent 8–9 year old's curiosity (and bridging naturally to Science).
"""

from __future__ import annotations

from typing import Any

from google import genai
from google.genai import types

from . import thinking
from .config import FALLBACK_MODEL, HYDROGEN_MODEL, genai_client

CURATED_PACKS: list[dict[str, Any]] = [
    {
        "id": "obsidian_truth",
        "title": "Real Obsidian vs. Video-Game Obsidian",
        "sources": [
            "Source 1 (Geology): Real obsidian forms when lava cools so fast that atoms cannot line up into crystals, turning the lava into natural volcanic glass.",
            "Source 2 (Physics): Because obsidian has no crystal grain, freshly fractured obsidian blades are sharper than steel surgical scalpels—down to 3 nanometers thick.",
            "Source 3 (Engineering): Unlike video-game obsidian that survives TNT blasts, real volcanic glass is extremely brittle and shatters if struck by a heavy hammer.",
        ],
        "inference_prompt": "Inference Check (Reading C2.3 / C3.2): Write one complete sentence using 'although' or 'but' explaining why real obsidian makes a terrible fortress wall despite being sharper than steel.",
        "paragraph_steps": [
            "Sentence 1 (Topic Sentence): State what real obsidian actually is and how lava creates it.",
            "Sentence 2 (Sharpness Detail): Explain why obsidian blades can be sharper than steel using 'because'.",
            "Sentence 3 (Contrast Conclusion): Contrast video-game obsidian with real obsidian using 'unlike' or 'although'.",
        ],
    },
    {
        "id": "bombardier_beetle",
        "title": "The Bombardier Beetle's Boiling Chemical Cannon",
        "sources": [
            "Source 1 (Anatomy): Inside its abdomen, the bombardier beetle stores two harmless liquids in separate reinforced chambers so they cannot react early.",
            "Source 2 (Chemistry): When a predator grabs the beetle, a valve mixes both chemicals in a reaction chamber, heating the spray to 100°C—as hot as boiling water.",
            "Source 3 (High-Speed Camera): High-speed X-ray video revealed the spray fires in 500 tiny pulses per second, letting the chamber cool slightly between blasts so the beetle doesn't cook itself.",
        ],
        "inference_prompt": "Inference Check (Reading C2.3): Write one complete sentence using 'because' or 'if' explaining what would happen to the beetle if its valve sprayed one continuous stream instead of pulses.",
        "paragraph_steps": [
            "Sentence 1 (Topic Sentence): Introduce the bombardier beetle and its boiling defense weapon.",
            "Sentence 2 (Causal Mechanism): Explain how the two chambers trigger the 100°C blast using 'when'.",
            "Sentence 3 (Survival Detail): Explain how pulsed firing protects the beetle using 'so' or 'because'.",
        ],
    },
    {
        "id": "trebuchet_physics",
        "title": "Counterweight Trebuchets: Gravity Siege Engines",
        "sources": [
            "Source 1 (Mechanics): Unlike catapults that rely on twisted ropes, a medieval trebuchet uses a massive box of stones—up to 10,000 kilograms—hanging on the short end of a pivoting beam.",
            "Source 2 (Energy Transfer): When crews pull the release pin, gravity drops the heavy counterweight and whips the long arm + leather sling upward at high speed.",
            "Source 3 (Architecture): Because trebuchets smashed flat stone walls from 300 meters away, castle engineers began building round towers that deflected boulders sideways.",
        ],
        "inference_prompt": "Inference Check (Reading C2.2 / C2.4): Write one complete sentence using 'so' or 'because' explaining how trebuchets changed the shape of medieval castles.",
        "paragraph_steps": [
            "Sentence 1 (Topic Sentence): Define how a counterweight trebuchet differs from a rope catapult.",
            "Sentence 2 (How It Fires): Describe what happens when the release pin is pulled.",
            "Sentence 3 (Historical Impact): Explain how castle builders adapted to trebuchet attacks.",
        ],
    },
    {
        "id": "metal_acoustics",
        "title": "How Heavy Metal Guitar Distortion Actually Works",
        "sources": [
            "Source 1 (Electromagnetism): An electric guitar string does not make loud sound by itself; steel strings vibrate over magnetic pickups, generating a tiny electrical signal.",
            "Source 2 (Signal Clipping): Early tube amplifiers overloaded when turned past maximum volume, chopping off the smooth peaks of the sound wave into jagged square-like waves.",
            "Source 3 (Acoustics): Heavy metal engineers realized that clipped waves pack extra high-frequency harmonics, making a single power chord sound massive and aggressive instead of broken.",
        ],
        "inference_prompt": "Inference Check (Reading C2.3 / C3.2): Write one complete sentence using 'because' or 'when' explaining how an accidental amplifier overload became the signature sound of heavy metal.",
        "paragraph_steps": [
            "Sentence 1 (Topic Sentence): Explain how an electric guitar turns string vibrations into electricity.",
            "Sentence 2 (Wave Clipping): Describe what happens to the smooth sound wave when an amplifier overloads.",
            "Sentence 3 (Musical Effect): Explain why metal guitarists use clipped waves on purpose using 'because' or 'so'.",
        ],
    },
    {
        "id": "hydrothermal_vents",
        "title": "Deep-Ocean Black Smokers: Ecosystems Without Sunlight",
        "sources": [
            "Source 1 (Extreme Depth): Two kilometers beneath the ocean surface, zero sunlight reaches the seafloor and crushing water pressure exceeds 200 atmospheres.",
            "Source 2 (Superheated Chimneys): Volcanic cracks called black smokers blast 400°C mineral-rich water upward, yet the immense ocean pressure stops the water from boiling into steam.",
            "Source 3 (Chemosynthesis): Because plants cannot use photosynthesis in total darkness, giant tube worms rely on bacteria that turn toxic vent chemicals into food.",
        ],
        "inference_prompt": "Inference Check (Reading C2.3): Write one complete sentence using 'because' or 'although' explaining how life survives around black smokers with zero sunlight.",
        "paragraph_steps": [
            "Sentence 1 (Topic Sentence): Describe the extreme conditions around deep-ocean black smokers.",
            "Sentence 2 (Physics Detail): Explain why 400°C vent water does not boil into steam using 'because' or 'although'.",
            "Sentence 3 (Biology Conclusion): Explain how tube worms and bacteria build a food chain without sunlight.",
        ],
    },
]

PACK_GEN_SYSTEM = """You are a science & history writer creating a 3-Source Reading-to-Write Research Pack for a smart Grade 3–4 reader (Ontario Strand C Comprehension + D1.3 Research from 3+ sources + D2.1 Informational Writing).
Given a topic, write THREE fascinating, 100% factual, non-babyish 1–2 sentence mini-sources (Source 1, Source 2, Source 3), ONE inference prompt requiring a complete causal/contrastive sentence, and a 3-step informational paragraph guide.
Never invent fake facts. Keep every source crisp and concrete.
Return strict JSON:
{"id":"custom","title":"...","sources":["Source 1: ...","Source 2: ...","Source 3: ..."],
 "inference_prompt":"Write one complete sentence using 'because' or 'although' explaining ...",
 "paragraph_steps":["Sentence 1 (Topic): ...","Sentence 2 (Mechanism): ...","Sentence 3 (Impact): ..."]}"""


def pick_pack(already_used: list[str] | None = None, custom_topic: str = "") -> dict[str, Any]:
    if custom_topic.strip():
        try:
            client = genai_client()
            for model in (HYDROGEN_MODEL, FALLBACK_MODEL):
                try:
                    r = client.models.generate_content(
                        model=model,
                        contents=f"Topic requested by student: {custom_topic}",
                        config=types.GenerateContentConfig(
                            system_instruction=PACK_GEN_SYSTEM, temperature=0.3, response_mime_type="application/json"
                        ),
                    )
                    out = thinking._json(r.text)
                    if isinstance(out, dict) and len(out.get("sources") or []) >= 3:
                        return out
                except Exception:
                    continue
        except Exception:
            pass

    used = set(already_used or [])
    for p in CURATED_PACKS:
        if p["id"] not in used:
            return p
    return CURATED_PACKS[0]
