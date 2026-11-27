# Pesu demo script

Record in Chrome at `http://localhost:3000` (`docker compose up --build`). For the child screens, use a phone-size window (DevTools → device toolbar, 390×844) or a real phone over USB with `adb reverse tcp:3000 tcp:3000`.

Speak into the mic if you can. Judge Mode buttons are the fallback, and they go through the same scoring code.

## 90-second path

| Time | Screen | Do | Say |
|---|---|---|---|
| 0:00 | Home | Show the two roles | "Speech therapy is once a week. Practice is supposed to happen every day at home, but nobody there can tell if the sound was right. Pesu listens on those six days." |
| 0:12 | Parent → Kavin → Start | Crow appears, prompt plays, ring turns green | "The child hears the therapist's own voice, then a two-note sound and a green ring: your turn." |
| 0:25 | Practice | Say **"kaakka"** (or *Says it right*) | "Right k: the crow flies away, a star goes in the jar." |
| 0:35 | Practice | Say **"taakka"** (or *Says the t-version*) | "The mistake Pesu listens for. No buzzer: a tilt, 'innoru thadava', the therapist's model sound, one more try." |
| 0:50 | Practice | *Parent speaks along* → tap ✓ | "When Pesu isn't sure, it never guesses. The parent decides, with the right sound to compare against." |
| 1:05 | Therapist (PIN 1234) → Kavin → Review | Play a try, press ✗, open history | "The therapist hears every try, sees what Pesu decided, and her ear is final. Pesu tracks how often it agrees with her." |
| 1:20 | — | — | "One docker compose command, no API keys." |

## 3-minute path

Do the 90-second path, then add:

| Time | Screen | Do | Say |
|---|---|---|---|
| 1:30 | Practice | *Says the English word* | "Mixed language isn't wrong: 'Tamil-la sollu'." |
| 1:40 | Practice | *TV on (before listening)* → Ready | "If the room is noisy, Pesu doesn't listen. Noise never becomes a wrong answer." |
| 1:55 | Practice | *Silence* ×6 | "If the child walks away, Pesu stops and asks if they're still here, instead of prompting an empty room." |
| 2:10 | Done → Summary | Press ▶ | "The parent gets one sentence: 'innaiku k sound 2-la 2 sari'." |
| 2:20 | Today → Sticker garden | Show | "Rewards only grow: one sticker per finished session. No streaks to lose." |
| 2:30 | Therapist → Kavin → Fast-forward → Review (14 days) | Show the chart, per-word table, agreement | "Two weeks of sample data: the trend, the hardest word, and Pesu's agreement with the therapist." |
| 2:45 | Setup | Show Export ZIP and Delete | "Families own their data: export or delete in one step." |
| 2:55 | — | — | "Pesu: practice by speaking, in Tamil, between sessions." |

## Tips

- Practise once first: Chrome asks for mic permission only once.
- If Chrome hears your "taakka" as காக்கா (it autocorrects), say it so: "the recogniser autocorrected me; that's why the therapist hears the audio and can override." Then use the Judge Mode button. Don't hide it.
- Keep the video under 3:00.
