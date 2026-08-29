# Synthetic fixture — invented characters, no real game content.
# The dedupe trap: prof's ONLY line in busy_hallway is a duplicate of an
# earlier line, so global dedupe by text drops it. Anything that counts the
# speakers surviving in the corpus sees a two-person scene that is really a
# three-person one — and resolves confidently to the wrong addressee.

label quiet_corner:

    mc "Finally some peace and quiet."
    nora "Yeah."

label busy_hallway:

    mc "Have you seen my notebook?"
    nora "Not since yesterday, I think."
    prof "Yeah."
