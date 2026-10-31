# Start VidGen Studio (local AI) when you log in

Nothing here is installed automatically. Both files stay in the project; you copy one into your own
Library folder.

## Try it first (changes nothing)
```
bash docs/autostart/autostart_local.sh --dry-run
```

## Install (one command)
```
cp docs/autostart/com.vidgen.local.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.vidgen.local.plist
```
It runs at every login: opens Docker Desktop if needed, starts postgres and redis, then starts the
app with `VIDGEN_AI_MODE=local`. Open http://localhost:5173 after about a minute.

## Remove
```
launchctl unload ~/Library/LaunchAgents/com.vidgen.local.plist && rm ~/Library/LaunchAgents/com.vidgen.local.plist
```

## Notes
- Log: `.dev/autostart.log` (plus `.dev/launchd.*.log`). Stop the app with `scripts/dev_down.sh`.
- The models load when you generate a preview, not at login, so they stay out of memory in between.
  An opt-in warm-up setting (`VIDGEN_WARM_UP_ON_START`, off by default) is being added.
- The plist contains the project path `/Users/singla/Developer/video-generator`. Edit it if you move the project.
- To make Docker itself start at login: Docker Desktop, Settings, General, "Start Docker Desktop when you sign in".
