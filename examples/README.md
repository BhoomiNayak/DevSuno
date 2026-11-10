# Demo examples

Six buggy snippets — one per check family the local analyser handles.
All code is synthetic. No real credentials, no real data.

| File | Bug | Check |
|---|---|---|
| `null_check.py` | `process_scores()` indexes `scores` with no None guard | `python-none-guard` |
| `off_by_one.js` | Loop runs `i <= arr.length`, reads past the last element | `off-by-one-bound` |
| `bare_except.py` | `except:` swallows every error silently, returns None | `bare-except` |
| `hardcoded_secret.py` | `STRIPE_API_KEY`, `DATABASE_PASSWORD` as string literals | `hardcoded-secret` |
| `unclosed_file.py` | `f = open(...)` without `with` block — leaks file handle | `unclosed-file` |
| `mutable_default.py` | `def add_item(item, cart=[])` — shared state across calls | `mutable-default-arg` |

---

## Suggested spoken questions (Hinglish)

Record any of these on your phone (8 seconds), copy to `question.wav`,
and pass with the matching `--file`.

### null_check.py
```
"bro check karo is array me null check kyun miss ho gaya"
```
```
devsuno ask --audio question.wav --file examples/null_check.py --play
```

### off_by_one.js
```
"ye loop last element pe kyun undefined de raha hai"
```
```
devsuno ask --audio question.wav --file examples/off_by_one.js --play
```

### bare_except.py
```
"bro ye function kabhi bhi error nahi deta lekin result bhi galat aata hai
 kya koi exception silently swallow ho rahi hai"
```
```
devsuno ask --audio question.wav --file examples/bare_except.py --play
```

### hardcoded_secret.py
```
"bro is file mein koi security issue hai kya password ya api key
 hardcode toh nahi kar diya"
```
```
devsuno ask --audio question.wav --file examples/hardcoded_secret.py --play
```

### unclosed_file.py
```
"bro ye file operations sahi se close ho rahi hain ya koi resource leak hai"
```
```
devsuno ask --audio question.wav --file examples/unclosed_file.py --play
```

### mutable_default.py
```
"bro ye function pehli baar theek kaam karta hai but dusri baar
 purana data kyun aa raha hai list khali honi chahiye thi"
```
```
devsuno ask --audio question.wav --file examples/mutable_default.py --play
```
