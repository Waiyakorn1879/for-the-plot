# Synthetic fixture — invented screen definitions, no real game content.

define gui_title = _("Pocket Cafe")

screen status_panel():
    frame:
        vbox:
            label "Status"
            text "Affection level"
            text "[affection_points]"
            textbutton "Continue":
                action Return()
                tooltip "Go to the next scene"

screen empty_panel():
    text ""

label after_screens:
    $ note = _("Saved to slot one") + _("Overwrite?")
    hero "Back to dialog."
