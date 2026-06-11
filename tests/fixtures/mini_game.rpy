# Synthetic fixture script — invented mini visual novel, no real game content.
# Exercises: say lines, escaped quotes, python blocks, $ lines, comments,
# menu choices with/without if, show text, narrator, vars/tags/escapes, dupes.

label start:

    # This comment must not be extracted
    $ affection = 0

    init python:
        def helper():
            return "this python string must not be extracted"

    scene bg cafe with dissolve

    hero "Hello there, [partner_name]!"
    hero "She said \"hold the door\" and left."
    partner "I'm {b}really{/b} glad you came."

    "The rain kept falling outside the cafe."

    show text "CHAPTER ONE"

    menu:
        "Order a coffee":
            hero "One espresso, please."
        "Leave the cafe" if affection > 0:
            hero "Maybe another day.\nI should go."

    partner "I'm {b}really{/b} glad you came."

    hero "(She seems happier today.)"

    return
