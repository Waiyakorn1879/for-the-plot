# Being a DIK — EP1 Character Profiles
## Translation Reference Guide (Thai)

---

## TRANSLATION CONSTANTS (Never Translate)
- Character names: name, Josy, Maya, Sage, Isabella, Quinn, Cathy, Camila, Jill, Troy, Derek, Tommy, Rusty, Jacob, Jamie, Tybalt, Chad, Steve, Magnar, Sally, Jade, Riona, Dawe, Anthony, Jill, Leon, Nick, Mona, Arieth
- Organizations: DIK, HOT, HOTs, DIKs, B&R, Burgmeister & Royce, Alpha Nu Omega, tri-betas, tri-alphas
- Locations: Bella Vista, Riverside
- Brands/Products: Burger Pharma, Dr PinkCake
- Game terms: [name], [mc_josy], [mc_maya], etc. (all `[variables]`)
- All Ren'Py tags: `{i}`, `{b}`, `{color=...}`, `{font=...}`, `{size=...}` and their closing tags
- Sound/action cues inside `*{i}...{/i}*`: translate the descriptive text but keep all markup

---

## CORE TRANSLATION RULES

1. **Register matching**: Each character has a distinct voice. Never let their voices bleed into each other.
2. **NSFW content**: Preserve the register and explicitness. No sanitizing.
3. **DIK/CHICK splits**: The same character (MC mostly) may sound slightly different based on the game path but strings are extracted without branching context — translate at a middle ground unless the text itself makes the path obvious.
4. **Internal monologue** `(...)`: MC's thoughts, always parenthesized. Keep parentheses. Should feel like inner voice, not narrated prose.
5. **Action text** `*{i}Softly moans{/i}*`: Keep asterisks and italic tags. Translate the action description.
6. **%%**: Literal percent sign in Ren'Py. Preserve as `%%`.

---

## CHARACTER PROFILES

---

### MC (mc) — The Protagonist
**Strings: 1,067 — the dominant voice of the game.**

**Background:** College freshman, raised by a single working-class father after mother died at birth. Learned carpentry and martial arts from dad. Plays guitar. Insecure beneath the bravado, but genuinely kind. Leaves hometown girlfriend-figure Josy behind.

**Personality:** Player-shaped — can be crude and aggressive (DIK path) or thoughtful and considerate (CHICK path). Both versions share: dry humor, self-awareness, occasional self-deprecation.

**English patterns:**
- Direct speech: casual contemporary, no formality
- Profanity: heavy on DIK path ("What the FUCK did I just walk into?"), lighter on CHICK
- Inner monologue: stream-of-consciousness in `(...)`, often insecure or observational
  - "(...it feels like the warmest hug.)"
  - "(I'm such a loser!)"
  - "(This is my only shot if I want to make a move on her.)"
- Shouts in CAPS when very angry: "TELL ME WHO STOLE IT!"
- Frequently uses: "Well...", "I guess", "Yeah", "Nah", "Dammit"

**Thai register:**
- Base register: ภาษาชายหนุ่มอายุ 18 ปี — "กู/มึง" กับผู้ชาย, "ผม" กับผู้หญิง
- **กับผู้ชาย** (Derek, Rusty, Tommy, Jacob, Leon, Nick, DIKs, จ๊อก, Chad): ใช้ "กู/มึง" เสมอ
- **กับผู้หญิงที่ไม่สนิท/formal** (Isabella, Cathy, Jill, Camila, Arieth, คนไม่รู้จัก): ใช้ "ผม" เสมอ
- **กับผู้หญิงที่สนิทและใช้ภาษาหยาบเอง** (Maya, Josy, Riona, Melanie, Sarah): "เรา" เสมอ
- **กับ Sage** (เพื่อนสนิทที่สุด): "เรา/แก" เสมอ — Sage ก็ใช้ "เรา/แก" กับ MC เช่นกัน
- **กับ Quinn** (dominant/confrontational): "เรา" หรือ "กู" ตาม scene (กู OK ใน NSFW/confrontation)
- **Inner monologue** `(...)`: ใช้ "กู" เสมอ — เป็นความคิดภายใน ไม่ได้พูดกับใคร
- DIK path speech: คำด่าแบบตรงๆ เช่น "ห่า", "เหี้ย", "แม่ง" — ใช้ได้กับทุกคนในบริบทที่เหมาะ
- Shouting: ใช้ CAPS ตามต้นฉบับ
- Self-deprecating humor: แปลให้รู้สึกว่า "รู้ตัวว่าโง่" ไม่ใช่แค่บ่น

**Key phrases to watch:**
- "(Fuck...)" → "(ห่า...)" / "(เหี้ย...)"
- "(This is it, [name]. It's now or never.)" → รักษา rhythm แบบกำลังใจตัวเอง
- "What the hell!?" → "นี่มันเรื่องอะไรกัน!?" หรือ "ห่าอะไรเนี่ย!?"

---

### Josy (js) — The Hometown Sweetheart
**Strings: 215**

**Background:** MC's coworker at summer job. Bubbly, talkative, knows it and apologizes for it. Waiting list for B&R. Has a stepbrother who got in unfairly. In a complicated relationship that she's conflicted about.

**Personality:** Enthusiastic and warm. Laughs easily ("Haha!"). Opens up about herself but is also emotionally vulnerable — the kiss scene shows she has real feelings for MC but feels guilty. Optimistic despite setbacks.

**English patterns:**
- Constant enthusiasm: "Did you!? Wow, that's awesome!"
- Frequent "Haha!" as a real laughing filler, not dismissive
- Hesitation: "Erm...", "..."  when shy or uncertain
- Direct when rejecting Steve: "FUCK OFF!"
- Warm and teasing with MC: "Haha, yeah, I tend to talk a lot."
- Vulnerable: "I'm so sorry...", "I didn't mean for this to happen..."
- Playful: "Scoot forward and make space for my cute butt."

**Thai register:**
- ภาษาสาวรุ่นใหม่ สบายๆ ใจดี ใช้ "เธอ/ฉัน" หรือ "นาย/ฉัน"
- เสียงหัวเราะ "Haha!" → "ฮ่าๆ!" หรือ "อิอิ" ขึ้นกับบริบท (ใหญ่ใช้ฮ่าๆ, เล็กๆ ใช้อิอิ)
- ความลังเล "Erm..." → "เอ่อ..." หรือ "อืม..."
- เวลาโกรธ: ยังดูเป็นผู้หญิงอยู่ ไม่ใช้คำด่าหนักเท่า Sage
- เวลาเสียใจ/ขอโทษ: น้ำเสียงเศร้า ไม่ใช้คำด่า

**Key phrases:**
- "Farewell? You're still coming back to visit, right?" → รักษาความห่วงใย
- "It's goodbye...not farewell..." — สำคัญมาก ความต่างระหว่าง "ลาจาก" กับ "ลาก่อน" → ใช้ "ลาก่อน ไม่ใช่ อำลา"

---

### Maya (my) — The Witty Neighbor
**Strings: 315 — second most lines after MC.**

**Background:** Local freshman, grew up near B&R. Derek's sister (though she hides this initially). Has family issues with her dad (ultimatum about HOT pledging). Has a boyfriend. Wants to pledge HOT for tuition money.

**Personality:** Confident, sarcastic, but genuinely friendly. Calls people out directly. Quick with comebacks. Hides vulnerability behind humor. Practical: "I need that money."

**English patterns:**
- Direct and frank: "A bunch of sluts, if you ask me." then immediately "Well, I'm still gonna pledge their house."
- Casual profanity woven naturally: "Shit, now I feel bad for you."
- Teasing: "Haha! Damn, [name]. You've barely been here an hour and are already making enemies?"
- Firm when pushed: "No, I don't {b}need{/b} someone to share my dorm with."
- Playful interrogation: "Interesting..." (after each answer in the café quiz)
- Calling out nonsense: "Wait, why are we discussing vaginas?"
- Insults to Derek: "Put some fucking clothes on, Derek!!!"

**Thai register:**
- ภาษาสาวที่ฉลาดและมั่นใจ ใช้ "ฉัน/เธอ" หรือ "ฉัน/นาย" เสมอ — **ไม่ใช้ กู/มึง เด็ดขาด** แม้กับเพื่อนสนิท
- พูดตรงแต่ไม่หยาบ เว้นแต่จะโกรธจริงๆ
- เวลาแซว: ใช้ tone ล้อเล่น ไม่ใช่ดูถูก
- เวลาพูดเรื่องเงิน/ครอบครัว: น้ำเสียงจริงจังขึ้นทันที ตัดคำแซว
- กับ Derek: อารมณ์พี่น้อง ระคายเคืองแต่รัก

**Key phrases:**
- "I'm different too." → ท้ายฉาก สำคัญ เป็น moment ที่เธอเปิดใจ แปลให้มีน้ำหนัก
- "That's some cool fucking stories in the making there, bro!" → ประโยคของ Derek แต่ Maya ก็ใช้สไตล์ใกล้เคียงกัน

---

### Derek (de) — The Chaos Gremlin
**Strings: 133**

**Background:** Party animal, Maya's brother. Lost his shirt (literally). Wants to join DIKs but doesn't want to fight a jock. Shamelessly honest: "I'm just here for the pussy."

**Personality:** High-energy, unfiltered, uses people (including his sister) to get what he wants but in a charming way. Calls MC "ass man" (if player chose that option). Celebrates every bad situation as an adventure.

**English patterns:**
- Bro energy: "Dude", "bro", "Holy fuck!", "No way!"
- Enthusiastic observations: "Did you see the tits on that one?"
- Backhanded honesty: "That's some cool fucking stories in the making there, bro!"
- Cheerleading MC: "And not everyone hates you. I like you!"
- Short punchy sentences when excited

**Thai register:**
- ภาษาผู้ชายวัยรุ่น เป็นกันเอง
- **กับผู้ชาย** (MC, Rusty, Tommy, Jacob, DIKs, jocks): ใช้ "กู/มึง" เสมอ
- **กับผู้หญิงทุกคน** (รวม Maya น้องสาว): ใช้ "เรา" — ไม่ใช้ กู/มึง กับผู้หญิง
- พลังงานสูง ประโยคสั้น
- "bro" → "เพื่อน", "ว่ะ" at end of sentences
- ความตื่นเต้นแบบอ่อนหัด ไม่ใช่ mature

---

### Sage (sa) — The Sorority President
**Strings: 62**

**Background:** HOT sorority president. Dating Chad (jock) who's cheating on her. Aggressive and direct. Knows her worth. Enlists MC to investigate Chad's infidelity.

**Personality:** Blunt, foul-mouthed, doesn't tolerate BS. Can warm up if you match her directness. Hates being talked down to. Hates vague answers.

**English patterns:**
- Shouted commands: "FUCK OFF!!!", "It's Sage! Fucking learn to listen."
- Cutting observations: "Nothing? Not even my G-strings go that high up."
- Direct propositions: "I want you to find out who Chad's been fucking behind my back."
- Sarcasm: "Found your voice?" (when MC stays quiet)

**Thai register:**
- ภาษาผู้หญิงที่ดุและตรง ใช้ "เรา/แก" กับ MC (EP2 เป็นต้นไป)
- **EP1 exception:** Sage ใช้ "เรา/นาย" — เพิ่งรู้จักกัน ยังไม่สนิท (MC ใช้ "ผม/คุณ" กลับ)
- กับเพื่อนหญิงสนิท (Quinn, Sarah): ใช้ "กู/มึง" ได้ — F-to-F register หยาบกว่าปกติ
- ไม่มีความสุภาพเทียม พูดอย่างไรก็อย่างนั้น
- คำด่า: ใช้เต็มที่ "ห่า", "เหี้ย", "แม่ง"
- เวลาขอบคุณ: สั้น ห้วน ไม่ยืดยาด

---

### Isabella / "Ice Queen" (isa) — The Librarian
**Strings: 44**

**Background:** Campus librarian. Cold exterior, warm heart. Magnar calls her "the Ice Queen." Scolds people for shenanigans. Consistently calls MC "boy" (condescendingly). Secretly helps him when he's in trouble.

**Personality:** Formal, strict, economical with words. No-nonsense. But when MC mentions his dead mother, she immediately softens. Her warmth is shown through actions (giving clothes), not words.

**English patterns:**
- Terse commands: "No." / "Sit!" / "TOWEL!"
- Formal reprimand: "Where are your manners, boy?"
- Measured questions: "Start from the beginning. Tell me why you ended up in that bush naked, boy."
- Rare warmth: "It's ok. Go on." / "Yes, well, that would make quite a difference."
- Never uses slang or profanity

**Thai register:**
- ภาษาทางการ สูงอายุกว่า ใช้ "คุณ" หรือ "เธอ/ฉัน" แบบเย็นๆ
- "boy" → "เด็ก" (ดูถูกเล็กน้อย) หรือ "น้องชาย" (condescending)
- ประโยคสั้น กระชับ มีน้ำหนัก
- เวลา scold: ไม่ตะโกน แต่เสียงหนักแน่น น่ากลัว
- เวลาอ่อนโยน: ยังคงสั้น แค่ tone เปลี่ยน

---

### Quinn (qu) — HOT Vice President
**Strings: 111**

**Background:** Vice president of HOT sorority. Caught MC sneaking in for panties. Dominant, calculating, likes having power over people.

**Personality:** Commanding and unapologetic. Uses MC's (player-chosen) name "pervert" as his nickname. Orchestrates situations to keep herself in control. Not above being sexually provocative as a power move.

**English patterns:**
- Direct commands: "Strip!", "Jack him off.", "Stop it!"
- Domineering narration during NSFW: "Look at that hard cock!", "She's such a slut."
- Mocking: "I bet this guy's a virgin." / "Coming in here trying to jack off to little girls. That's fucking disgusting!"
- Control freak: "You're in no position to be calling the shots here."

**Thai register:**
- ภาษาผู้หญิงที่มีอำนาจ ใช้ "เธอ/ฉัน" หรือ "มึง/กู" ขึ้นกับโทน
- กับเพื่อนหญิงสนิท (Sage, Sarah): ใช้ "กู/มึง" ได้ — F-to-F register
- คำสั่ง: กระชับ หนักแน่น
- NSFW: อ่านออกว่าเธอ enjoy การควบคุม ไม่ใช่แค่บรรยาย
- เรียก MC ว่า "ไอ้โรค" หรือ "[mc_quinn]" ตามต้นฉบับ

---

### Cathy (ca) — English & Math Teacher
**Strings: 80**

**Background:** MC and friends' English and Math teacher. Professional. Organizes campus tour. Strict about rules (no alcohol on campus).

**Personality:** Dedicated teacher, somewhat flustered by Derek's outbursts, but maintains control of the classroom. In MC's dream: playfully flirtatious (completely out of character — played for comedy).

**English patterns:**
- Professional announcements: "Class dismissed.", "Pencils down, class."
- Tour guide: "Much like the students before you and the students to come..."
- Flustered by Derek: "Young man, you are free to leave if you don't wish to—"
- Dream sequence: teasing, playful, unlike real Cathy

**Thai register:**
- ในห้องเรียน: ภาษาครูมาตรฐาน ทางการแต่ไม่แข็ง ใช้ "นักเรียน/ครู"
- ฉากทัวร์: ภาษาทางการ ชัดเจน
- ฉากฝัน: ภาษาเย้ายวน ผิดปกติจากตัวละครปกติ (ตลกเพราะ contrast)

---

### Troy (troy) — The Hostile Roommate
**Strings: 37**

**Background:** MC's original dorm mate. Former jock, kicked out of the team. Doesn't want to share his dorm with anyone. Territorial and aggressive.

**Personality:** Angry, explosive, territorial. Short fuse. Barely tolerates MC's existence. Guilt-stricken when guitar is stolen (he couldn't prevent it) but still won't show vulnerability.

**English patterns:**
- Territorial aggression: "Who the fuck are you!?", "Find somewhere else to sleep."
- Dismissal: "Shut up.", "Leave me alone."
- Explosive: "I SAID GET THE FUCK OUT!!!"
- Reveals guilt but masks it with anger: "You think I wanted this!?"

**Thai register:**
- ภาษาหยาบมาก ใช้ "กู/มึง" ตลอด
- ประโยคสั้น หยาบ ก้าวร้าว
- ไม่มีความสุภาพเลย
- เวลาออกคำสั่ง: ขีดเส้น ชัดเจน

---

### Dad (dad) — MC's Father
**Strings: 103**

**Background:** Single working-class father. Never went to college. Worked construction. Met and fell in love with MC's mom despite class difference. Gave MC a jar of savings for college.

**Personality:** Warm, loving, rambles when telling stories (famously forgets details). Uses "son" affectionately. Wise advice delivered in a casual, imperfect way. Emotional about MC going to college.

**English patterns:**
- Rambling: "It took her three days...no, wait, five days? Hm...maybe something along the lines of a week?"
- Warmth: "I love you, son." / "I'm proud of you, son."
- Awkward parenting: "Please know that there's no shame in putting on a condom."
- Philosophical: "If something's meant to be, it will happen, son."

**Thai register:**
- ภาษาพ่อไทยชนชั้นกลาง-ล่าง อบอุ่น ใช้ "พ่อ/ลูก"
- ไม่ทางการ ใช้ภาษาพูดทั่วไป
- เวลาพูดพล่าม: รักษา rhythm ของการลืมรายละเอียด ให้รู้สึก authentic
- เวลา emotional: น้ำเสียงหนักขึ้น ไม่ดราม่า แต่จริงใจ

---

### Tommy (tm) — DIK Alpha Male
**Strings: 26**

**Background:** The top DIK, wins drinking contests. Crude and dominant.

**Personality:** Boisterous, the loudest guy in the room. Competitive. Rules the DIK house with crude bravado.

**English patterns:**
- Competitive trash talk: "Fucking learn how to drink, Jacob!"
- Crudeness as power: "I get more tits in my mouth these days than I did back then."
- Dominance: "This is a DIKs only house."

**Thai register:**
- ภาษาผู้ชายหัวหน้ากลุ่ม ดัง หยาบ มีอำนาจ
- ใช้ "กู/มึง" หรือ "พวกมึง" ตลอด
- พูดดัง พูดชัด

---

### Rusty (rs) — DIK Member
**Strings: 23**

**Background:** DIK member. More reasonable than Tommy. Acts as early advocate for MC.

**Personality:** Laid-back, fair-minded within DIK culture. Uses "dude."

**Thai register:**
- ภาษาเพื่อน สบายๆ ใช้ "กู/มึง" หรือ "พวกเรา"
- น้ำเสียงเป็นกันเอง ไม่ก้าวร้าวเท่า Tommy

---

### Jacob (jac) — DIK Member
**Strings: 10**

**Background:** DIK member who witnessed MC's wedgie and defends him at the DIK house.

**Personality:** Jokey, mischievous, gossips.

**Thai register:** เพื่อน สบายๆ แซวตลอด

---

### Steve (st) — The Entitled Summer Job Guy
**Strings: 19**

**Background:** Boss's son at summer job. Entitled, tries to impress Josy with the car his dad owns. Antagonizes MC.

**Personality:** Overconfident, delusional about Josy's interest. Turns mean when challenged. Uses "Come on, Josephine" despite her corrections.

**English patterns:**
- Persistent flirting: "Come on, Josephine. Don't be like that."
- Entitlement: "I'll be the owner of this place one day, you know!"
- Dismissal: "That saves me the trouble of firing you."

**Thai register:**
- ภาษาผู้ชายที่คิดว่าตัวเองเท่ ใช้ภาษาปกติแต่มีความหยิ่ง
- เวลา bragging: ขึ้นจมูก น้ำเสียงดูถูก
- เวลาโกรธ: ระเบิดง่าย

---

### Chad (ch) — The Jock Bully
**Strings: 16**

**Background:** Alpha jock (tri-alphas). Sage's cheating boyfriend. Intimidating.

**Personality:** Aggressive, territorial, short sentences. Uses force first.

**Thai register:**
- ภาษาสั้น แข็ง ก้าวร้าว
- ใช้ "กู/มึง" หรือ "แก/กู" แบบข่มขู่

---

### Tybalt (ty) — Prep Fraternity President
**Strings: 3**

**Background:** Alpha Nu Omega president. Rich family donates to B&R. Dismissive of MC.

**Thai register:** ภาษาทางการ มีชนชั้น ดูถูกแบบ subtle ไม่พูดมาก

---

### Magnar (mg) — Tri-Beta President
**Strings: 40**

**Background:** Nerd fraternity president. Intellectual, a bit condescending but friendly.

**Personality:** Proper but not stuffy. Proud of his intelligence. Plays Dungeons and Gremlins. Has a dry sense of humor.

**English patterns:**
- Formal but warm: "Please, be seated." / "Well, this was fun, [name]."
- Dry humor: "Hm...I guess that we could use someone to take notes for us."
- Geeky: "Think of her as the protector of knowledge."

**Thai register:**
- ภาษาทางการมากกว่า MC แต่ไม่เป็นทางการเท่า Isabella
- ฉลาดแกมโกง น้ำเสียงนักวิชาการ
- ใช้ "ผม/คุณ" ตลอด

---

### Jade (ja) — Dream Sequence Character
**Strings: 74**

**Background:** A woman MC notices in the cafeteria. Appears only in a dream sequence.

**Personality:** Sultry, direct in the dream. Teasing.

**Thai register:**
- ภาษาเย้ายวน ตรงไปตรงมา ลักษณะครู/ผู้ใหญ่ → MC ใช้ **ผม** กับเธอเสมอ (ไม่ใช้ กู)
- NSFW: เต็มที่ ตรง ไม่อ้อมค้อม แต่ MC ยังคง ผม

---

### Camila (cam) — New HOT Pledge
**Strings: 8**

**Background:** New HOT pledge doing an initiation. Passive, follows Quinn's instructions.

**Thai register:** ภาษาสาวที่ไม่แน่ใจตัวเอง ตามคำสั่งคนอื่น

---

### Jill (ji) — Kind Stranger
**Strings: 45**

**Background:** Meets MC after wedgie incident. Sweet, hates bullying. Seems to know Tybalt.

**Personality:** Genuinely kind, empathetic, light sense of humor.

**English patterns:**
- Empathy: "Argh! I can't stand bullies. Some boys never grow up."
- Light humor: "Hahaha!" (at MC's "dislodge something from my ass" comment)
- Warmth: "Stay safe, [name]."

**Thai register:**
- ภาษาสาวใจดี สุภาพ อ่อนโยน ใช้ "เธอ/ฉัน"
- ไม่ใช้คำด่า เว้นแต่จะตกใจมาก

---

### Minor Characters

**Boss (bs):** Short, authoritative. Power-tripping convenience store manager. **Register: สั้น กระชับ ทางการแบบปลอมๆ**

**Reception Lady (rc):** Professional but slightly weary. **Register: ทางการ งานราชการ**

**Heather (hg) / HOT girls:** Reaction lines mostly. Casual. **Register: สาวมหาวิทยาลัย**

**Riona (ri):** DIK-adjacent. Brief appearance, observational. **Register: ธรรมดา สบายๆ — MC ใช้ เรา/แก**

**Sarah (sar):** HOT sister, snarky/crude. **Register: กู/มึง เสมอ** (แม้กับ MC) — F-to-F กับ Sage/Quinn ก็ กู/มึง

**Melanie (ml):** HOT sister, gossip-oriented. **Register: ฉัน/เธอ — MC ใช้ เรา/แก**

**Rose (ro):** Pink Rose dancer. **Register: ฉัน/นาย — MC ใช้ เรา (กู เฉพาะ peak NSFW เท่านั้น)**

**Envy (en):** Pink Rose dancer, Swyper. **Register: ฉัน/นาย — MC ใช้ เรา (กู เฉพาะ peak NSFW เท่านั้น)**

**Lily (ly):** HOT pledge / strip club dancer. **Register: ฉัน/นาย — MC ใช้ เรา (กู เฉพาะ peak NSFW เท่านั้น)**

**Ashley (ash):** HOT pledge, nervous. **Register: หนู/ฉัน — MC ใช้ ผม**

**Security (sec):** Short commands. **Register: ทางการ ราชการ**

**Dawe (dw):** Jock minion, sneaky. **Register: หยาบ ล้อเล่นแบบมีเจตนาร้าย**

**Anthony (an):** Jock minion, naive/stupid. **Register: โง่ๆ เป็นลูกสมุน**

**_narrator:** Pure narration, no speaker. **Register: ทางการ เป็นกลาง คำบรรยาย**

**_menu:** Player choice text. **Register: กระชับ ชัดเจน คำสั้น สื่อความหมายได้**

**_text:** On-screen text (tutorials, notifications). **Register: ทางการ คำแนะนำ**

---

## COMMON PHRASES & CONSISTENCY TABLE

| English | Thai | Notes |
|---------|------|-------|
| Yeah / Yep | ใช่ / อือ / เออ | context-dependent |
| Nah / Nope | เปล่า / ไม่เอา | informal |
| What the hell | นี่มันเรื่องอะไรกัน / ห่าอะไรเนี่ย | by character |
| For fuck's sake | ห่า / แม่ง | informal, context |
| Dude / Bro | แก / เพื่อน / ว่ะ | male speech |
| Holy shit | ห่าอะไรเนี่ย / โอ้โห | context |
| Come on | เฮ้ / เอาน่า / มาเลย | context |
| Whatever | ก็ได้ / ช่างเถอะ / ไม่เป็นไร | |
| Actually | จริงๆ แล้ว / ที่จริง | |
| I guess | ก็น่าจะ / มั้ง | |
| Anyway | อย่างไรก็ตาม / งั้นก็ | |
| Wait | เดี๋ยวก่อน / โอ้โห เดี๋ยวนะ | |
| Fine | โอเค / ก็ดี / ก็ได้ | |
| Sorry | โทษที / ขอโทษ | by formality |
| Thanks | ขอบคุณ / ขอบใจ / โอ้โห ขอบคุณ | by formality |
| Damn | ห่า / เหี้ย | light profanity |
| Fuck (excl.) | เหี้ย / ห่า / แม่ง | |
| Fuck (v.) | เย็ด | NSFW context |
| Ass | ตูด / ก้น | crude vs normal |
| Tits | นม | NSFW |
| Dick / Cock | ควย / อวัยวะ | NSFW / normal |
| Pussy | หี / อวัยวะ | NSFW |
| Hot (attractive) | โคตรเซ็กซี่ / น่าดึงดูด | context |

---

## NSFW TRANSLATION NOTES

- Preserve explicitness: if the original is graphic, the Thai should be equally graphic
- "cock" → "ควย" in NSFW contexts
- "tits/boobs" → "นม" always in these contexts
- "ass" → "ตูด" in crude contexts, "ก้น" in milder ones
- "slut" → "อีร่าน" / "อีสำส่อน" (derogatory, keep the bite)
- "pussy" → "หี" in explicit contexts
- Sexual action descriptions: direct, visual, no euphemisms
- Quinn's commanding tone during NSFW must read as dominant authority, not clinical narration
