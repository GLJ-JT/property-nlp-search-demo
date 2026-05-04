# Research Notes

## Product observations

- Renters often search in fragments, not full sentences.
- The same intent can appear as a positive request, a negative constraint, or a soft preference.
- Landmarks and stations matter as much as the listing itself.
- Trust drops quickly when the system returns obvious false positives.

## Design direction

- Keep natural language input visible.
- Reveal extracted filters immediately.
- Keep normal filters in place for control.
- Use plain-language reasons for ranking.
- Make the launch copy benefit-led, not technical.

## Evidence from the prototype

- 50 ranking stress cases passed.
- 100 negative leak cases passed.
- the data model separates verified facts from derived search fields.
- the engine supports hard filters, soft preferences, and exclusions.

## External signals observed

- Property portal pages often blend structured facts with agent copy and repeated "close match" inventory, which makes negative exclusions and explainable ranking important.
- Property search pages visibly support filters, map/list discovery, and saved alert behavior, which supports the idea that smarter intent handling should augment, not replace, normal controls.
