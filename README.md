# Goal Hunter SQLite state

This branch holds versioned SQLite records for Goal Hunter alerts and in-play snapshots. The main branch holds the code. GitHub Actions uses a separate worktree and commits every durable transition here before sending Telegram.

Do not put tokens, group chat IDs or secrets in this SQLite file. This repository is public; match events and message IDs are visible. Do not edit the database by hand. Old commits consume storage and are not unlimited.
