# Property NLP Search Case Study

## Problem

The diagnosis moved from "can property search understand natural language?" to "how does a renter know the system understood the messy parts of their request?"

A query like "studio near UCL under 2500, bills included, lift, quiet, not basement" does not map neatly to one control. It mixes budget, location, amenities, exclusions, and soft preferences in one sentence. Standard filters make the renter split that sentence apart and remember the rest while scanning listings.

The product risk is confidence leakage. If users cannot see that their requirements have been understood, they create their own comparison workflow through screenshots, notes, agent messages, or another portal.

## Proposal

I kept the normal search and filter model, then added a visible interpretation layer. The system parses messy renter language into structured intent, shows that intent back as editable chips, separates hard exclusions from soft preferences, and explains why each result ranked where it did.

## What should and should not happen

The prototype should prove understanding before asking for trust. It should keep the existing search bar and filter logic, add intent chips below the query, explain ranking clearly, and let users correct the interpretation. It should not replace the whole portal search model, hide normal filters, pretend to be production ready, or turn a concept into a revenue claim without live validation.

## Tech stack

This prototype is intentionally lightweight. It uses a Python parser and scorer, structured JSON property data, geo and synonym enrichment, and static article surfaces for GitHub Pages. Editable chips and explainable ranking are the interaction model, not a hidden layer.

## Modelled outcome

The expected UX change is not a cleverer search box for its own sake. It is fewer moments where users wonder whether the system forgot a constraint. If that confidence holds, the search session has a better chance of reaching shortlist, save, share, or enquiry behaviour before the user leaves to compare elsewhere.

Any revenue uplift should be treated as a modelled opportunity, not a hard claim.

In plain terms, the concept aims to make the renter's intent visible enough that they can stay inside the product longer before moving the same search into another channel.

## Testing and critique

Because this was a solo concept built under time and resource constraints, I used stress prompts to test edge cases, exclusions, and ranking leakage. That gave useful prototype evidence, but it is still not live market proof.

## Self-critique

What I did right was make the problem legible, keep the flow explainable, and build a working backbone rather than a static mock. What I would avoid next time is overclaiming revenue certainty, hiding too much behind the model, overfitting to one user segment, or pushing the concept past the evidence available.

## Current vs projected UX

In the current experience, the renter types a messy query and filters may help, but intent is still mostly hidden. The user compares across listings and other channels, and the search session can leak before a shortlist forms.

In the projected experience, the renter types the same messy query, the system parses it into chips and visible constraints, ranking explains itself in plain language, and the user can correct the search before trusting the results.

## Revenue view

The revenue discussion should stay modelled, not invented. The concept does not prove uplift. It argues that if visible intent reduces search leakage, the product has a clearer path to better retention, enquiry quality, and premium search packaging.

## Reflection

The next proof point would be live query data: what renters type, which chips they edit, which constraints cause empty results, which explanations increase confidence, and whether shortlist or enquiry behaviour improves against the normal filter flow.
