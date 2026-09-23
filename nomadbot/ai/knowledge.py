"""Real, sourced facts about The Nomad Network.

Everything here comes from two sources the founder provided directly: the
website brand doc ("More info for The Nomad Network website.docx") and the
full message history of the Announcements group. Nothing here is inferred or
guessed — the whole reason this file exists is that the bot had no real facts
before it, only an instruction to "only talk about Nomad Network things,"
which is a scope, not knowledge.

Kept separate from persona.py (tone) and each handler's FUNCTIONAL_RULES
(safety/behaviour constraints) on purpose — this is the third, distinct
layer: content. Composed as PERSONA + KNOWLEDGE + FUNCTIONAL_RULES in both
channels, so the voice can be casual, the facts stay exact, and the
behaviour constraints still win if any of the three ever pull apart.
"""

KNOWLEDGE = """FACTS ABOUT THE NOMAD NETWORK — treat everything below as ground truth. If
something isn't covered here and wasn't said earlier in this conversation,
say plainly that you don't know rather than guessing or inventing it. This
applies especially to the website URL: it is EXACTLY https://thenomadnetwork.online
— never state any other domain, and specifically never "nomad.network".

BRAND OVERVIEW
The Nomad Network is a modern ecosystem for people who refuse to settle —
people who believe there's always another level to reach and are committed
to continuous growth. The aim: help these people advance and move higher.
One meaningful relationship, one opportunity, one event, or one
collaboration can completely change the trajectory of someone's life — so
the network exists to make discovering opportunities, meeting exceptional
people, and creating meaningful work easier than ever. What started as an
event discovery community is evolving into a global platform where people
can learn, build, collaborate, create, and belong.

VISION
To become the world's most influential modern network for people going
places — powering global relationships, collaboration, culture, and
opportunity through experiences, technology, and community infrastructure.
A future where being part of The Nomad Network gives members social
capital, access, visibility, and real-world leverage anywhere in the world;
where members can land in any city and instantly find community,
opportunities, collaborators, and a sense of belonging.

MISSION
Curating experiences while building a digital ecosystem with physical
representations, and an intentional community that helps people form
meaningful relationships beyond surface-level networking. Through events,
experiences, partnerships, community systems, content, and technology, the
network creates environments where members can meet high-value people,
discover opportunities, build lasting collaborations, expand globally,
learn socially, gain visibility, and find belonging. Depth over vanity
metrics.

THE ECOSYSTEM — four initiatives under one mission
- Event Nomad: the flagship. Helps Nomads discover experiences that move
  their careers and lives forward — events across the globe, across 6+
  industries, career/job opportunities, workshops, accelerator programs,
  grants, hackathons, startup opportunities and more. One of the
  fastest-growing event discovery communities for ambitious people.
- Nomad Labs: "where talent meets opportunity." Brings together outstanding
  talent from within the network to build products, solve problems, execute
  client work, and collaborate on ambitious ideas. Members get access to
  freelance opportunities, startup collaborations, hackathons, product
  experiments, job recommendations, team formation, and creative
  partnerships. People don't just network here, they build together.
- Nomad Studios: "stories that move people." The creative studio behind The
  Nomad Network — brand storytelling, content strategy, event coverage,
  creative campaigns, photography, videography, community marketing, social
  media content, design. Exists to help ideas look, feel, and spread like
  world-class brands.
- The Nomad Letters: the intelligence layer. A contributor-powered
  publication capturing and distributing the ecosystem's collective
  knowledge — deep expertise, diverse topics, perspectives and insights from
  Nomads, to help people broaden their thinking and grow across every
  dimension of life.

WHERE IT'S HEADED
Evolving beyond event discovery into a complete opportunity ecosystem:
learning, funding, research & development, talent discovery, digital
identity, creator economy infrastructure, community technology, and global
city chapters.

WHO'S IN THE NETWORK
Developers, designers, financial traders, product managers, marketers,
founders, Web3 enthusiasts, AI builders, creators, community managers,
freelancers, professionals, investors, career switchers, students — with one
thing in common: a desire to keep learning, building, and growing.

VALUES
Intentionality (meaningful relationships are built deliberately, not
randomly), Access (reducing friction between talented people and
opportunities/knowledge/relationships/influential rooms), Excellence
(premium standard in everything, from branding to communication), Community
(people grow faster together), Curiosity (lifelong learners who explore,
experiment, evolve), Authenticity (genuine conversations over performative
networking), Global Mindset (thinking beyond borders, industries, local
limitations), Reciprocity (great communities are built on contribution —
create value, don't just consume it).

HOW THE TELEGRAM COMMUNITY ACTUALLY WORKS (from the Announcements group)
The Telegram community is called "Event Nomad." Groups/channels members use:
- Nomad Lounge — general chat, ideas, tips, vibing with other Nomads.
- Introductions and Networking — where new members post their intro (repost
  from Nomad Lounge): name, what they do, city, interests, a fun fact.
- Event Drops — where events get shared (IRL and online). Members react
  with ⚡️ on events they've registered for and plan to attend. Searchable by
  city, event tag/industry, or date using the group's built-in search.
- Highlights and Reviews — members share pictures, videos, and key
  takeaways from events they attended.

Getting started, in order: pin the group and turn on post notifications →
introduce yourself in Nomad Lounge, then repost in Introductions and
Networking → explore Event Drops → share highlights/reviews after attending
something → engage in Nomad Lounge → if you find an event worth sharing,
reach out to an Admin or Scout.

Members are encouraged to share events AND opportunities (in any industry)
they come across, anywhere in the world, whether or not they're personally
attending — the more relevant events/opportunities someone shares, the
better their chances of earning the "Scout" role.

Event hashtags: #ANomadIsHere (posting live at an event), #ANomadWasHere
(posting a highlight/review afterward). Members who attend an event The
Nomad Network posted about can invite the network's Instagram account as a
collaborator when sharing content about it.

There's also a WhatsApp channel ("Event Nomad Updates") that sends short
update nudges pointing people back to Telegram for full details:
https://whatsapp.com/channel/0029Vb6Jd3dHrDZfzdlm7E3g

Nomad Labs applications are open via https://bit.ly/JoinNomadLabs — capped
at 10 submissions per month by design, for people who are intentional, know
what they bring, and are ready to put it to work. Selected Nomads get access
to opportunities across the ecosystem: direct client recommendations,
project referrals, collaborations, paid engagements, and work alongside
other exceptional Nomads.

The Nomad Network has an announced partnership with Chromes Network.

KrediLoop (https://krediloop.xyz) is a product being built by a member of
the network, not an official Nomad Network product — it reimagines the
traditional Ajo/savings-circle model as a digital way for communities to
save together and build a verifiable credit history. Its waitlist was shared
in the community as something Nomads might want to support or get early
access to.

The official website, https://thenomadnetwork.online, is live — it has more
info about the network and its initiatives, and is the right place to point
someone who wants to learn more or is being introduced to the network for
the first time."""
