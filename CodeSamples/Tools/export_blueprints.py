"""Run inside Unreal Editor (Python) to export Blueprint assets as T3D text.

Example (headless):
    UnrealEditor-Cmd.exe RoadTrip.uproject -ExecutePythonScript="export_blueprints.py" -unattended -nullrhi

Then convert the .t3d files (UTF-16) with blueprint_to_text.py.
"""
import os
import unreal

OUT_DIR = os.environ.get("BP_EXPORT_DIR", os.path.join(os.getcwd(), "bp_export"))
BLUEPRINTS = [
    "BP_RoadTripQuestManager", "BP_SurvivalComponent", "BP_InventoryManager",
    "BP_QuestNPC", "BP_QuestPickup", "BP_SearchableItem",
    "BP_RegionSupplyPickup", "BP_CarAutoUpgrade", "BP_Dice",
]

os.makedirs(OUT_DIR, exist_ok=True)
for name in BLUEPRINTS:
    asset = unreal.load_asset(f"/Game/Blueprints/{name}.{name}")
    if not asset:
        unreal.log_warning(f"Blueprint not found: {name}")
        continue
    task = unreal.AssetExportTask()
    task.object = asset
    task.filename = os.path.join(OUT_DIR, name + ".t3d")
    task.automated = True
    task.replace_identical = True
    task.prompt = False
    unreal.Exporter.run_asset_export_task(task)
