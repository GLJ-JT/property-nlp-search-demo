# Case Study Draft

## Problem

A modern property portal already has a strong search surface, including street-level search and familiar filters. The bigger gap is that most portals still do not support natural-language search as a first-class layer.

That matters because many renters, especially relocation-heavy and high-net-worth users, do not want to start by speaking to agents across XHS, WeChat, Telegram, or WhatsApp. If the first query is strong enough, the app can hold them earlier, keep them inside the product longer, and reduce leakage into other channels.

The broader business issue is not awareness. It is trust at the moment of intent. If the portal cannot understand what the renter means, the renter leaves to compare elsewhere and then comes back later with the same intent copied into a different channel.

## Proposal

This proposal builds a lightweight NLP concept that sits on top of the current flow. The user can still search normally, but the system also parses messy natural language into structured intent, shows that intent back as editable chips, and explains why each result ranked where it did.

## What should and should not happen

It should keep the existing search bar and filter logic, add intent chips below the query, explain ranking clearly, and make the user feel in control. It should not replace the whole portal search model, hide the filter system, pretend to be production ready, or suggest teamwide adoption without validation.

## Tech stack

This prototype is intentionally lightweight. It uses a Python parser and scorer, structured JSON property data, geo and synonym enrichment, and static article surfaces for GitHub Pages. Editable chips and explainable ranking are the interaction model, not a hidden layer.

## Modelled outcome

The projected UX is a stickier search session, fewer early handoffs to agents, more saves and shares, and a better chance of converting high-intent users before they leave the platform.

Any revenue uplift should be treated as a modeled opportunity, not a hard claim.

In plain terms, the concept aims to keep the renter inside the portal longer before they speak to agents elsewhere, which is where the leak usually starts.

## Testing and critique

Because this was a solo concept built under time and resource constraints, I used AI-generated stress prompts to test the UX validity. That gave useful signals around edge cases, exclusions, and ranking leakage, but it is still a concept, not live market proof.

## Self-critique

Likely pitfalls include overconfident parsing, weak synonym coverage, bad agent-copy data, users who prefer normal filters first, and revenue claims that sound too certain. It would improve with more real-world testing, stronger geo data, broader multilingual coverage, and better governance around rights and data before any production use.

## Current vs projected UX

In the current experience, the renter types a messy query, filters may help, but intent is still mostly hidden, the user compares across listings and other channels, and the search session leaks before a shortlist forms. In the projected experience, the renter types the same messy query, the system parses it into chips and visible constraints, ranking explains itself in plain language, and the user stays inside the flow long enough to shortlist, save, and share.

## Revenue view

The revenue discussion should stay modeled, not invented. The concept does not prove uplift. It argues that fewer users leaking into off-platform negotiation should improve the odds of conversion, retention, and return visits.

## Reflection

What I did right was make the problem legible, keep the flow explainable, and build a working backbone rather than a mock idea. What I would avoid next time is overclaiming revenue certainty, making the system feel too magical, overfitting to one user segment, or pushing the concept past the evidence available.
