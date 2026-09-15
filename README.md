# Heroes of the Storm - Archipelago World

## Setup Guide

1. **Install the APWorld** from [Releases](https://github.com/POD-io/HotS-ArchipelagoWorld/releases/latest).
2. **Generate a multiworld** - Include the YAML (see `Heroes of the Storm.yaml`) when generating the Archipelago multiworld.
3. **Launch the client** - Open the Archipelago Launcher and start the **Heroes of the Storm Client**.
4. **Play normally** - Play Quick Match, Versus AI, or any other mode in HotS. Use heroes you have unlocked from the multiworld.
5. **Checks from replays** - After each game, HotS saves a replay. The client will detect and read the replay file automatically and send any completed checks.



## Party Mode

**Party Mode** builds the seed for a group on **one Archipelago slot** — not multiple AP slots. Leave it off for a normal solo seed.

Personal hero checks do **not** change. Party does not drop damage, takedowns, or other hero challenges. It changes **how heroes are handed out**.

### Solo (Party Mode off)

The current game. One host, `/name` matches **your** account(s), extra starting heroes and role passes work as usual. This is the default.

### Party Mode on

The seed is **built for N seats**. Use this when the group is the point: everyone should have a hero to play, not sit in spawn waiting for a single unlock.

- **Party Size** 2–5: each wave has that many heroes.
- **Starting Waves** 1–3 (default 1): how many waves you start with. 2–3 is a bench.
- Roles in a wave are **random**. A role only repeats after every role still in the leftover pool has been used. Plando `start_inventory` can force a named starter; nothing else pins Tank/Healer.
- **Role Passes**, **Extra Starting Heroes**, and **Shards Per Hero** are ignored.
- After the starting waves, the rest of the pool is still grouped the same way. Each later group is unlocked by one **Progressive Hero Wave**. The first copy unlocks the next stack, the second copy the stack after that, and so on. `!hint Progressive Hero Wave` hints those copies; the Unlocks tab lists which heroes are in each wave.
- Goal, dailies, and per-hero checks stay the same. Goal heroes are kept off the *starting* waves when the pool allows, then appear in a later wave.

**Playthrough vs solo:** Solo finds one hero (or a shard stack) at a time, often gated by a role pass. Party starts N playable heroes. Checks on those heroes can contain **Progressive Hero Wave** items. Each copy is another full party, in the order generated for that seed.

A leftover smaller than party size is folded into the previous wave so you do not get a one-hero “wave” that leaves people idle.

## Replay Scoring

Who this client credits from a replay. Works with or without Party Mode. YAML sets the seed defaults; change anytime with `/credit` (saved per seed).

| Mode | Who is scored |
| --- | --- |
| **me** | Only you (`/name`) |
| **team** | Unlocked heroes on your team |
| **match** | Unlocked heroes in the game |

Leave Credit Names empty to score everyone that mode allows, **or** list scoreboard names. In the client: `/credit team` then `/credit add FriendName`. `/name` is you, not the friend list.

Everyone can run a client with **me**. One person scoring for friends: **team** or **match** on that one client.

### Two clients, one slot

Location checks (a win, a talent, “deal 25k”) are a set: sending Jaina’s win twice does nothing.

**Cumulative stats and dailies add.** Two clients on **team** or **match** will double those totals.

- Everyone running a client → **me**
- One client for friends → **team** or **match** on that client

Loot, stims, and talent tomes are local to each client.

## Troubleshooting / Technical Details



### Replay folder detection

On connect, the client looks for replay folders under:

`Documents\Heroes of the Storm\Accounts\`

It scans for any subfolder named `Multiplayer` and watches for new `.StormReplay` files.

On first run, if nothing is found, the client opens normally and asks for your replay folder path in the **console input** at the bottom of the client window. Paste the path and press Enter.

Settings are saved in `hots_config.json` in your Archipelago user data folder. To change the folder later, edit that file:

```json
{
  "replay_dirs": [
    "C:\\Users\\<username>\\Documents\\Heroes of the Storm\\Accounts\\12345678\\1-Hero-1-12345678\\Multiplayer"
  ]
}
```

Or paste the path when prompted on first launch. Restart the client after editing the file.

### Scoring commands

`/name` is you. `/credit` is who else this client scores.

| Command | Description |
| --- | --- |
| `/name Player1` | Set your scoreboard name |
| `/name remove Player1` | Remove one name |
| `/name clear` | Clear your names |
| `/credit` | Show status + usage |
| `/credit me` | Only you |
| `/credit team` | Your team |
| `/credit match` | Whole lobby |
| `/credit add Player2` | Limit team/match to listed names |
| `/credit remove Player2` | Remove one listed name |
| `/credit clear` | Clear name filter (everyone allowed by mode) |
| `/credit ai on` / `ai off` | Credit computer players |
| `/credit reset` | Restore seed YAML defaults |
| `/rescan` | Reprocess latest replay |

### Rescanning the latest replay

Existing replays are ignored when you connect, only new matches after that are processed automatically.

To re-check your most recent game (missed checks, wrong name, etc.):

/rescan
This reprocesses the newest .StormReplay in your configured folder(s) and sends any new checks.

### Client Commands


| Command               | Description                                   |
| --------------------- | --------------------------------------------- |
| `/hots`               | Unlocked heroes, credit status, open checks   |
| `/heroes`             | Unlocked vs locked heroes                     |
| `/goal`               | Goal mode and progress                        |
| `/name`               | Who you are on this client                    |
| `/credit`             | Scoring: me / team / match, add names         |
| `/rescan`             | Reprocess your latest replay manually         |
| `/builds`             | Write talent checks to TalentBuilds.txt       |
| `/stim`               | Use a Stimpack (also on the Loot tab)         |

