# Code Samples

**Roadtrip** is a Blueprint-only Unreal Engine project, so its logic lives in binary `.uasset` files that GitHub cannot show. To make the work readable, I exported the gameplay Blueprints from Unreal Engine 5.8 and converted each node graph into plain-text pseudo-code. The full project is not published because most of its content is third-party asset packs.

> **AI assistance:** Some of the Blueprint logic and the export tooling were written with AI assistance. I was responsible for the design, integration and debugging.

## What to read first

| System | File | Highlights |
|---|---|---|
| Quest progression | [`Blueprints/BP_RoadTripQuestManager.txt`](Blueprints/BP_RoadTripQuestManager.txt) | A stage machine (stages 0 to 15) across three regions. Distance checks to waypoints start travel stages, NPC quest states unlock the next stage, and each supply pickup advances the stage. |
| Quest NPCs | [`Blueprints/BP_QuestNPC.txt`](Blueprints/BP_QuestNPC.txt), [`BP_QuestPickup.txt`](Blueprints/BP_QuestPickup.txt) | A three-state quest (offer, return the item, done). The NPC checks the quest manager's stage first, then the player's inventory for the quest item. Pickups refuse to be taken until the owner has been spoken to. |
| Survival | [`Blueprints/BP_SurvivalComponent.txt`](Blueprints/BP_SurvivalComponent.txt) | An actor component. A looping timer drains hunger and thirst, and health drops once either is below the danger threshold. Every value is clamped and the component exposes one `AddSurvivalValue` entry point. |
| Inventory | [`Blueprints/BP_InventoryManager.txt`](Blueprints/BP_InventoryManager.txt) | Add, use and remove items, a quest-item flag, toggling the inventory UI with the right input mode, and applying item effects to the survival component. |
| Searching with dice | [`Blueprints/BP_SearchableItem.txt`](Blueprints/BP_SearchableItem.txt), [`BP_Dice.txt`](Blueprints/BP_Dice.txt) | A physics dice that is thrown with random impulse and torque, then read by comparing socket heights. Each searchable looks up the roll in a table of result ranges and applies health, hunger, thirst and item rewards. |
| Region supplies | [`Blueprints/BP_RegionSupplyPickup.txt`](Blueprints/BP_RegionSupplyPickup.txt) | Supplies can only be collected in the stage window of their own region. |
| Truck upgrades | [`Blueprints/BP_CarAutoUpgrade.txt`](Blueprints/BP_CarAutoUpgrade.txt) | A trigger volume that opens the upgrade store when the truck enters. |

## Design notes

**One manager owns the story.** `BP_RoadTripQuestManager` is the only place that stores the current stage. NPCs, pickups and supplies read it or ask it to advance, so a stage can be added or reordered in one place.

**One interaction entry point.** NPCs, pickups and searchables all expose the same `Interact` event (through the `BPI_Interact` Blueprint interface), so each object decides for itself what happens when the player interacts with it.

**Dice as a content table.** A search is a dice roll mapped to result rows (min, max, title, description, health, hunger, thirst, reward item). That makes outcomes designer-editable without touching the graph.

**Known limitations.** The inventory stores each item property in a parallel array, which is easy to break; a struct array or the existing `DT_Items` data table would be safer. The reward lookup in `AddRewardItem` is a long chain of string comparisons that should be a data table lookup. These are the first things I would refactor.

## How these files were made

Blueprints are binary assets, so these text files are generated, not hand-written:

1. [`Tools/export_blueprints.py`](Tools/export_blueprints.py) runs inside Unreal Editor (headless) and exports each Blueprint as T3D text.
2. [`Tools/blueprint_to_text.py`](Tools/blueprint_to_text.py) parses the nodes and pins, walks the execution wires, and prints pseudo-code (events, functions, branches, loops, casts, variable sets).

The pseudo-code leaves out node positions, comments and visual layout, and it is only a reading aid. The source of truth is the Blueprint itself.

Unreal Engine 5.8
