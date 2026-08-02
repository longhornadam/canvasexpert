> **Historical origin document.** This is the teacher's own early brainstorm for what became
> The former classroom-display concept (called "Glass," and before that "Scenes," at the time this was written). It is
> preserved here for context, not as a design authority: the terminology below ("Scenes,"
> "panes") and specific numbers (an 84% score floor) are both superseded. The current,
> historical only; the shipped score floor is
> `SCORE_FLOOR_PERCENT = 90` in `api/audience.py`.

CanvasExpert: Scenes (formerly Glass)

Basically a version of ClassroomScreen.com's service, but open-sourced and tied in with the rich information environment of CanvasExpert. Teachers will open the Scene, maximize it, and then  interact with it on their projector. there will be static information, time-shifting information, and widgets (timers, pickers, text boxes, audio boxes, etc...)

Just as a teacher's classroom's context changes as the day progresses, so changes the scene. By knowing the school calendar and bell schedule and teacher schedule, the Scene "knows" what information to show.

The teacher uses an AI agent (Claude Desktop or ChatGPT) via MCP and the AI authors the scene(s) per the conversation with the teacher. If something needs changing during the day, then the teacher talks to the AI agent who makes changes and offers a new Scene.

We need to build Scene templates and widgets. There will be functionality for users to build their own, but prebuilding the basics is key for testing and basic functionality.

Users will provide bell schedules and district academic calendars for basic functionality. Each day in school on the academic calendar must have a bell schedule attached, and this can be determined and updated as the teacher and AI talk.
Advanced information includes games, dances, clubs, tutorials, etc...

When the Scene is projected, users will be able to interact with it via mouse or touch (if the projector allows). the scene will have a persistent toolbar or corner icons for Maximize/Minimize, Close, etc...

Widgets should be interactive. Touching/clicking lets users close/remove it, interact with it in relevant ways (stop/start/reset timers, etc...)

User information relevant to Scenes is stored in the "Sync" area CE uses already. The AI agent via MCP instructions will know to ask the teacher for things like their teaching schedule if the information is not already present. 

Berry Miller's bell schedule and Pearland ISD's academic calendar will ship as defaults in the repo. Bell schedules are NOT PII. Academic calendars are NOT PII. Those are freely available and public information.

There is a Scenes (tbd) tab in CanvasExpert.

When the teacher clicks it, there is a left-hand column that travels with the content on the right-hand side (1/4 | 3/4)

Right-hand column options
- Active
	this shows the panes/scenes authored by AI via MCP (each has "Display" (which fullscreens for immediate use), "Archive" (which archives), and "Delete (which deletes) button
	presented in descending order by date/time created
- Templates
	this shows the teacher the different (named) templates available
- Archived
	archived scenes
- Widgets
	different pre-made widgets (also authorable)

PII Issues for the AI assistant writing via MCP

The AI assistant never needs to know the PII. It knows pseudonymized info and it knows that birthdays and such are stored and available. When the agent is writing, it generalizes "if birthday(s) available, then do this with them...). "I know the PII is over on the other side of CanvasMirror because a contract exists that tells me how it is formatted and where it will be, even though I can't see it"

PII Issues for CE/Glass (the local app)

Classroom-Facing: Names, birthdays, missing assignments, numerical scores above 84% (4+/5, etc...), positive achievements, STAAR Masters, Bell schedule, school schedule, events, games, performances, library hours, tutorial schedules, club schedules, teacher names, 
Teacher-Facing: grades below 84% (<4/5, etc...), behavioral punishment, Special Ed and 504 designations (this is the only one, basically, that results in challenges/lawsuits), social security #, address, phone #s, parent email, student ID #, economic designations, <STAAR Masters

It is common practice for schools to put birthdays, with full names, on signage outside the school. It is common for schools to publicly announce outstanding achievements (5 on AP tests, all A list, etc...). For positive things, we essentially ignore the scariest interpretations of FERPA. It is not the AI assistant's job to pretend to understand how FERPA works IRL, it is there to offer caution. If there is a question, the AI will ask the teacher and defer to the teacher. The AI will never consider something "locked" on its own; it must be on this list or be determined with active consent from the human teacher. You will assume opt-ins unless told otherwise (teacher's responsibility to tell you).


Primary Template Ideas:

"Scenes Base"
Top Bar

Middle in 2 columns

Left Column
Right column

Bottom bar

Top: Date, time, end-of-period time, course name
MiddleLeft: Today's agenda and learning/writing objectives
MiddleRight: Scrolling marquee of upcoming assignments and events
Bottom: interface icons (close, min/max, timer launch, widgets selector icon, etc...), scrolling marquee of birthdays, missing assignments
