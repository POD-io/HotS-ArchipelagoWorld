# Heroes of the Storm - Archipelago World

## Setup Guide

1. **Install the APWorld** from [Releases](https://github.com/POD-io/HotS-ArchipelagoWorld/releases/latest).

2. **Generate a multiworld** - Include the YAML (see `Heroes of the Storm.yaml`) when generating the Archipelago multiworld.

3. **Launch the client** - Open the Archipelago Launcher and start the **Heroes of the Storm Client**.

4. **Play normally** - Play Quick Match, Versus AI, or any other mode in HotS. Use heroes you have unlocked from the multiworld.

5. **Checks from replays** - After each game, HotS saves a replay. The client will detect and read the replay file automatically and send any completed checks.

## Troubleshooting / Technical Details

### Replay folder detection

On connect, the client looks for replay folders under:

`Documents\Heroes of the Storm\Accounts\`

It scans for any subfolder named **`Multiplayer`** and watches for new `.StormReplay` files.

On first run, if nothing is found, the client asks you to enter your replay folder path manually.

Settings are saved in **`hots_config.json`** in your Archipelago user data folder. To change the folder later, edit that file:

```json
{
  "replay_dirs": [
    "C:\\Users\\<username>\\Documents\\Heroes of the Storm\\Accounts\\12345678\\1-Hero-1-12345678\\Multiplayer"
  ]
}
```
Or paste the path when prompted on first launch. Restart the client after editing the file.

### Player name (Battle Tag)
The client matches replays to your slot using your in-game battle tag (player name).

Set in client: /name YourBattleTag
Or edit hots_config.json: "battle_tag": "YourBattleTag"
If replays are skipped, run /name with no args to compare your saved name vs. what your latest replay shows.

### Rescanning the latest replay
Existing replays are ignored when you connect, only new matches after that are processed automatically.

To re-check your most recent game (missed checks, wrong name, etc.):

/rescan
This reprocesses the newest .StormReplay in your configured folder(s) and sends any new checks.

### Client Commands

| Command | Description |
|---------|-------------|
| `/hots` | Unlocked heroes and open checks |
| `/goal` | Goal mode and progress |
| `/name YourBattleTag` | Set your HotS player name for replay matching |
| `/rescan` | Reprocess your latest replay manually |
