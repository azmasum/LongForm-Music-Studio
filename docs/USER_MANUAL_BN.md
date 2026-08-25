# LongForm Music Studio — ব্যবহার নির্দেশিকা (ইউজার ম্যানুয়াল)

সংস্করণ ১.০.০ · Windows 10/11

LongForm Music Studio (LFMS) এমন একটি ডেস্কটপ অ্যাপ যা YouTube, ডকুমেন্টারি,
পডকাস্ট, মেডিটেশন ইত্যাদির জন্য **দীর্ঘ দৈর্ঘ্যের ব্যাকগ্রাউন্ড মিউজিক** (১০–১২০+
মিনিট) তৈরি করে। সব মিউজিক অ্যাপের নিজস্ব synthesis engine দিয়ে **তৈরি হয়** —
কোনো গান কপি হয় না, তাই কপিরাইট claim-এর ঝুঁকি থাকে না।

> ভাষা-নোট: টেকনিক্যাল শব্দ (Seed, Genre, Preset ইত্যাদি) আসল UI-র সাথে মিল
> রেখে English-এই রাখা হয়েছে।

---

## সূচিপত্র

1. [ইনস্টল ও চালু করা](#1-ইনস্টল-ও-চালু-করা)
2. [অ্যাপের সাজানো — ৬টি পেজ](#2-অ্যাপের-সাজানো--৬টি-পেজ)
3. [প্রথম মিউজিক তৈরি](#3-প্রথম-মিউজিক-তৈরি)
4. [AI Music Director (ঐচ্ছিক)](#4-ai-music-director-ঐচ্ছিক)
5. [শোনা, Timeline ও Undo/Redo](#5-শোনা-timeline-ও-undoredo)
6. [Export ও Provenance সার্টিফিকেট](#6-export-ও-provenance-সার্টিফিকেট)
7. [Batch Render Queue](#7-batch-render-queue)
8. [Library — খোঁজা ও গোছানো](#8-library--খোঁজা-ও-গোছানো)
9. [Mixer](#9-mixer)
10. [সমস্যা ও সমাধান](#10-সমস্যা-ও-সমাধান)
11. [FAQ](#11-faq)

---

## 1. ইনস্টল ও চালু করা

### উপায় ১ — Portable ZIP (ইনস্টল ছাড়া)

1. GitHub Releases পেজ থেকে `LongFormMusicStudio-<ভার্সন>-portable.zip`
   নামান।
2. যেকোনো ফোল্ডারে unzip করুন।
3. `LongFormMusicStudio.exe` চালু করুন — Python বা অন্য কিছু লাগবে না।

### উপায় ২ — Setup.exe

`LongFormMusicStudio-<ভার্সন>-setup.exe` চালু করে wizard অনুসরণ করুন।
Start Menu shortcut ও (চাইলে) desktop icon তৈরি হবে; Settings → Apps থেকে
uninstall করা যায়।

### উপায় ৩ — Source থেকে (developer)

Python 3.10+ দরকার:

```powershell
pip install -e ".[dev,gui]"
python -m lfms.app
```

### ডেটা কোথায় থাকে?

- Source থেকে চালালে: `%APPDATA%\LongFormMusicStudio` — এর ভেতরে
  `Projects\`, `MusicLibrary\`, `Backups\`, `Exports\`, `Logs\` ইত্যাদি।
- Portable/installed build: portable mode-এ অ্যাপের পাশের data ফোল্ডার —
  পুরো ফোল্ডার কপি করলে library-সহ সব সরে যায়।
- Library database: SQLite + automatic backup (`Backups\`)।

---

## 2. অ্যাপের সাজানো — ৬টি পেজ

বাঁ দিকের sidebar থেকে পেজ বদলানো যায়:

| পেজ | কাজ |
| --- | --- |
| **Library** | তৈরি/import করা সব audio-র তালিকা, search, tag, favorite |
| **Generate** | নতুন মিউজিক তৈরির মূল form |
| **Batch** | একসাথে একাধিক track render করার queue |
| **Timeline** | clip সাজানো, undo/redo |
| **Mix** | channel volume/mute/solo |
| **Export & Provenance** | master করে WAV/FLAC deliver + সার্টিফিকেট verify |

নিচে **transport bar**: ▶ Play / ■ Stop এবং সময় দেখায়।

---

## 3. প্রথম মিউজিক তৈরি

**Generate** পেজে:

| Field | মানে |
| --- | --- |
| **Seed** | একই seed = হুবহু একই মিউজিক। **New seed every generate** টিক থাকলে (default) প্রতিবার Generate-এ নতুন গান হবে; reproduce করতে চাইলে টিক তুলে ফিক্সড seed ব্যবহার করুন বা **Random seed** চাপুন |
| **Genre** | মিউজিকের ধরন — AMBIENT, LOFI, DOCUMENTARY ইত্যাদি |
| **ইন্সট্রুমেন্ট** | seed অনুযায়ী ১৫টা synthesized voice থেকে lead/pad/bass বাছাই হয় — Piano, Electric Piano, Pluck, Nylon guitar, Bell, Marimba, Strings, Choir, Organ, Pad, Bass, Saw Bass, Kick, Hat, Snare |
| **Mood** | আবহ — CALM, DREAMY, NEUTRAL ইত্যাদি |
| **Duration** | মিনিট/সেকেন্ড — দীর্ঘ ভিডিওর জন্য যত দরকার |
| **Intensity** | 0–100; কম = ধীর-শান্ত, বেশি = busy/dense |

তারপর **Generate into timeline** চাপুন। কয়েক সেকেন্ডে track তৈরি হয়ে
timeline-এ চলে যাবে এবং library-তে নিজে নিজে register হবে (genre/mood tag
সহ)। Transport bar-এর Play চেপে শুনুন।

**টিপ:** ভিডিওর নিচে ব্যাকগ্রাউন্ড হিসেবে দেওয়ার আগে export preset হিসেবে
BACKGROUND_BED নিন (দেখুন §6) — ভয়েসওভারের সাথে লড়াই করবে না।

### 3.1 Reference track — কারো গানের মতো করে (কপি নয়)

Generate page-এ **"Reference track"** বক্সে যেকোনো অডিও ফাইল বাছলে (অথবা
সরাসরি .mp3/.wav/.ogg/.flac লিংক দিলে) LFMS ফাইলটা লোকালি বিশ্লেষণ করে তার
**BPM, key/mode, intensity, energy shape** ধার নিয়ে একই style-এর গান বানায়।

- মিউজিক **হুবহু কপি হয় না** — melody সবসময় নতুন; reference-এর শুধু "রঙ" ব্যবহৃত হয়
- বিশ্লেষণ সম্পূর্ণ offline, প্রথম ~৩ মিনিট যথেষ্ট
- YouTube/Spotify-জাতীয় লিংক ইচ্ছাকৃতভাবে কাজ করে না — অডিওটা নিজে save/export
  করে **Choose file…** দিয়ে দিন
- Generate-এর পর library item-এ `ref:…` tag থাকবে — কোন গান থেকে অনুপ্রাণিত
  তা পরে খুঁজে পাবেন

---

## 4. AI Music Director (ঐচ্ছিক)

বাংলা/English বাক্য লিখে প্যারামিটার suggest করানো যায় — যেমন:
*"২০ মিনিটের শান্ত meditation music"*।

- **Off থেকে শুরু** — ব্যবহার করতে হলে checkbox-এ consent দিতে হয়:
  *Enable AI director (I understand where my prompt is sent)*।
- **Provider দুটি:**
  - **Offline** — বাক্য আপনার PC-র ভেতরেই interpret হয়, কোথাও যায় না।
    Keyword (duration, mood, genre word) চিনে deterministic suggestion দেয়।
  - **Ollama** — prompt পাঠায় **আপনার নিজের চালানো localhost Ollama
    server**-এ; বাইরের কোনো cloud-এ যায় না। Ollama চালু না থাকলে provider
    available দেখাবে না।
- **Suggest parameters** চাপলে Seed/Genre/Mood/Duration form পূরণ হয়ে যায়;
  পছন্দ না হলে ম্যানুয়ালি বদলে Generate করুন।

---

## 5. শোনা, Timeline ও Undo/Redo

- **Play / Stop**: transport bar-এ; সময় `00:00 / 00:00` ফরম্যাটে দেখায়।
- **Timeline পেজ**: প্রতিটি generation একটি clip হয়ে বসে। Clip-এ label,
  fingerprint-এর প্রথম অংশ, duration দেখা যায়।
- **Undo/Redo**: menu থেকে বা
  - `Ctrl+Z` — Undo
  - `Ctrl+Shift+Z` — Redo

ভুলে কিছু generate/delete করলে Undo-ই বন্ধু। Timeline save/load হয়
project file-এ; crash হলে `Backups\`-এর শেষ backup থেকে ফেরানো যায়।

---

## 6. Export ও Provenance সার্টিফিকেট

**Export & Provenance** পেজে দুটি অংশ:

### Verify fingerprint

- **Generated item** combo থেকে item বেছে **Reload list**/**Verify
  fingerprint** চাপুন।
- অ্যাপ stored parameters দিয়ে মিউজিক re-generate করে fingerprint মিলিয়ে
  দেখে — ফল **VERIFIED** বা **FAILED**। এতে প্রমাণ হয় যে audio-টা সত্যিই
  ওই parameters দিয়ে তৈরি।
- **Save certificate (TXT/JSON)** দিয়ে প্রমাণপত্র ফাইল রাখা যায় —
  copyright dispute-এ জোর প্রমাণ।

### Render, master & deliver

1. Item বাছুন, **Preset** বাছুন:

| Preset | Loudness | কখন |
| --- | --- | --- |
| YOUTUBE | −14 LUFS | YouTube/Facebook upload |
| PODCAST | −16 LUFS | podcast platform |
| EBU R128 | −23 LUFS | broadcast মান |
| BACKGROUND_BED | −20 LUFS | ভয়েসওভারের নিচে ব্যাকগ্রাউন্ড |

2. **Choose folder…** → destination দিন → **Render & export**।

অ্যাপ নিজেই master (loudness normalize + true peak ceiling), QC gate পাস
করায়, WAV/FLAC লিখে library-তে export item register করে (tag:
`export`, `target:<preset>`), আর certificate ফাইল audio-র পাশেই রাখে।
Progress statusbar-এ দেখা যায়।

---

## 7. Batch Render Queue

একসাথে অনেক variation দরকার? **Batch** পেজে:

1. **Tracks** (কয়টি), **Duration each**, Genre/Mood/Intensity দিন।
2. **Mastering preset** বাছুন (উপরের §6 table)।
3. **Choose output folder…** দিন → **Enqueue batch**।

প্রতিটি track পায় **unique seed** — একই রকম দুটো বানানো হয় না। Queue worker
পেছনে চলে, UI freeze হয় না।

**Controls:** Pause/Resume · Cancel selected · Retry selected (failed job
আবার চালায়) · Move up/down (order বদল) · Clear finished।

Table-এ প্রতি job-এর status (PENDING/DONE/FAILED...), duration, realtime
factor দেখা যায়; নিচে rolling performance summary (avg speed) আসে।

**নোট:** একটা job fail হলে queue থেমে যায় না — বাকিগুলো ঠিকই হয়।

---

## 8. Library — খোঁজা ও গোছানো

- **Search box**: title, path, fingerprint বা tag দিয়ে খুলুন।
- **Tag filter** + **Favorites only**: তালিকা ছাঁটুন।
- **Favorite** button চাপলে star লাগে; **Delete**-এ entry যায়।
- **New collection… / Add to collection…**: project-ভিত্তিক গ্রুপ বানান।

প্রতিটি item-এর details-এ BPM, key, duration, loudness, fingerprint দেখা
যায়। Import করা audio-র license classification (CC0/public domain/user-owned)
ঠিক রাখুন — UNKNOWN/RESTRICTED হলে অ্যাপ স্পষ্ট warning দেখায় এবং কখনো
"copyright-free" বলে চালিয়ে দেয় না।

---

## 9. Mixer

**Mix** পেজে timeline-এর প্রতিটি channel-এর strip:

- Volume fader, pan
- **M** = Mute, **S** = Solo
- Effect chain edit (channel-ভিত্তিক)

Voiceover-safe ducking settings এখানেই tune করা যায় — কথা চলার সময় মিউজিক
নিজে নিজে নেমে আসে।

---

## 10. সমস্যা ও সমাধান

| সমস্যা | সমাধান |
| --- | --- |
| অ্যাপ খুলছে না | Antivirus quarantine log দেখুন; SmartScreen-এ *More info → Run anyway* |
| শব্দ নেই | Speaker output, transport Play, mixer mute/solo চেক করুন |
| Export FAILED | QC gate ব্যাখ্যা statusbar/message-এ পড়ুন; ভিন্ন preset বা নতুন folder try করুন |
| Job FAILED (batch) | row select করে **Retry selected** |
| Library হারায়নি কিন্তু ভুল দেখায় | `Data\` ফোল্ডার backup রাখুন; corrupt DB হলে নতুন ফাইলে শুরু করে backup থেকে restore |
| Crash report | data dir-এর `Logs\` ফোল্ডারে `crash_<সময়>.txt` ফাইল হিসেবে জমা হয় |

আরও বিস্তারিত: [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md)।

---

## 11. FAQ

**একই seed আবার দিলে কী হবে?**
হুবহু একই মিউজিক আসবে — deterministic engine। এটাই provenance verification-
এর ভিত্তি।

**তৈরি মিউজিকের উপর কি কপিরাইট claim করা যাবে?**
মিউজিক সম্পূর্ণ procedural/original; certificate + verified fingerprint
আপনার original-work প্রমাণ শক্ত করে। Imported audio-র license অবশ্য আপনার
দায়িত্ব।

**MP3 export আছে?**
v1.0-এ delivery WAV ও FLAC। MP3 দরকার হলে ফ্রি converter (যেমন ffmpeg)
ব্যবহার করুন।

**কি কি OS-এ চলে?**
Windows 10/11 (64-bit) target। Source থেকে Linux-এ core engine চলে, তবে
official support Windows।

**AI director কি internet ব্যবহার করে?**
না। Offline provider সম্পূর্ণ local; Ollama provider-ও আপনার নিজের machine-এ
localhost-এ কথা বলে। Consent না দিলে feature চলেই না।

---

*License: LFMS code MIT — বিস্তারিত README.md। আনন্দে মিউজিক বানান!*
