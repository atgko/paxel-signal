# Signal Weekly Research Digest
**Generated:** 2026-07-14
**Calls analyzed:** 2 calls (2025-05-01 to 2026-06-17)

---

## Top 5 Priorities This Week

### 1. GPO/Wholesaler Contract Data — Prominent, Auto-Populated, Centralized
**Who's asking:** Sales Rep (7 mentions — the single most-cited issue this period)
**What they need:** Reps are trained to look for GPO and wholesaler info first, every time, and it's not surfacing where they expect it. They also want pricing data to auto-populate from contract terms instead of manual lookup, and a single source of truth for contract status instead of periodically chasing the contracting team.
**In their words:** *"everything always as a rule you need to have GO wholesaler up top and I didn't see that anywhere but it has to be up top that's like our eye is trained to go there"*
**Recommended action:** Add a GPO/Wholesaler summary block to the top of the account and opportunity pages, and auto-populate the Contracts & Pricing section from the linked contract record when an opportunity is created.

### 2. Surface Lapsed and Declining Accounts as Opportunities
**Who's asking:** Sales Rep (5 mentions)
**What they need:** Reps are manually tracking reorder timing with sticky notes. They want the system to flag accounts that are overdue for a reorder based on historical cadence, and turn those into actionable opportunities automatically rather than requiring manual cross-referencing of purchase history against task lists.
**In their words:** *"If there's another one that said they bought from us a year ago and haven't bought since then, I kind of need to know that... due for purchase in the next month. So like I said, I got to keep track with 8,000 little sticky notes here"*
**Recommended action:** Build an automated "Reorder Due" flag on the account list, triggered when a customer's purchase interval exceeds their historical average cadence, and auto-generate a linked opportunity.

### 3. Real-Time Inventory Visibility
**Who's asking:** Sales Rep (3 mentions, escalating urgency — "you're going to hear me start to beat that drum every time we talk")
**What they need:** Reps are closing deals on volume they can't actually fulfill because they have no visibility into current inventory/allocation before committing units to a customer. This is causing broken commitments in the field, not just an inconvenience.
**In their words:** *"I personally sold 2,000. I closed a deal on 2,000 units and it end up that I could only give them 890... there's got to be data out there to where we know"*
**Recommended action:** Scope integration with inventory/allocation data source and add an inventory availability indicator to the product card before reps can log a committed unit volume on an opportunity.

### 4. Opportunity Close/Reopen Workflow Destroys Historical Data
**Who's asking:** Sales Rep (3 mentions)
**What they need:** Reps avoid closing opportunities because closing them makes historical data disappear — critical when discontinued products get relaunched a year or more later and all prior context is gone. They want a workflow that preserves history regardless of open/closed state.
**In their words:** *"there's tons of stuff that's open the company because we weren't going to sell that drug anymore closed all the ops so we can't even see them. they went away and then a year and a half later they decided we are going to sell that product again. So we lost all of that."*
**Recommended action:** Change opportunity "close" to an archive state (not a delete/hide state) that remains searchable and reportable, and stop requiring a new opportunity record on product relaunch.

### 5. Opportunity Field Auto-Population (GPO, Wholesaler, Stage, AMU, Naming)
**Who's asking:** Sales Rep (3 mentions)
**What they need:** Manual data entry on opportunity creation is costing reps meaningful time daily — GPO, wholesaler, stage, and average monthly usage are all derivable from existing account data but currently require manual entry.
**In their words:** *"if everything was just like bang, you're saving me that's at least one or two calls of savings amount of time over a day."*
**Recommended action:** Auto-populate GPO, wholesaler, stage, and AMU fields on opportunity creation from the parent account record, and auto-generate the opportunity name from account + product.

---

## Bugs Requiring Attention
- **Account search defaults to "owner" filter** — reps covering other territories or acting in cross-functional roles (e.g., customer support) get incomplete results and assume accounts don't exist. High priority, Search & Navigation. *"The biggest struggle that I have on the accounts page is that it defaults to searching by owner."*

---

## Data & Compliance Flags
- **New vs. recurring customer conflation in comp data** — system flags reorders from existing customers as "new" for incentive purposes, with no way to distinguish true new business from recurring revenue. Affects comp accuracy and rep trust in reporting. *"If it's new, I need to see a difference between that and someone that's just new visav the designation of the incentive plan."*
- **No source of truth for contract data** — reps manually chase the contracting team periodically because no centralized, authoritative contract list exists.
- **Rolling quarter reporting is misaligned with business reality** — the business operates month-to-month; quarterly views don't match how reps track quota or reorder cadence.
- **Meeting/task cards lack contextual identifiers** — contact cards don't surface account name, GPO, or wholesaler, making it hard to recall who a contact is at a glance.
- **Bulk-closing opportunities causes permanent data loss on product relaunch** — see Priority #4.

No compliance/legal flags identified this period.

---

## Needs Matrix

| Persona | Feature Request | Bug | Data Problem | UI Polish | Product Story | Compliance/Legal | Workflow |
|---|---|---|---|---|---|---|---|
| Sales Rep | 28 mentions | 3 mentions | 6 mentions | 8 mentions | 13 mentions | — | 3 mentions |
| Sales Director | — | — | — | — | — | — | — |
| VP/Advisor | — | — | — | — | — | — | — |

---

## Analyst Notes
This is one rep, but he's dense with signal, and the pattern is unmistakable: every top issue traces back to the same root cause — data that exists somewhere in the system but isn't surfaced where the rep is looking, or is thrown away when a record is closed. GPO/wholesaler visibility, contract auto-populate, inventory, and the opportunity-close data loss are really one problem wearing four hats: don't make reps hunt for or lose data they already gave you. Fix the account search default-to-owner bug now — it's a two-line fix with outsized daily friction. The month-vs-quarter dashboard restructuring can wait; it's a real complaint but low urgency compared to the data-loss and inventory issues, and it's a bigger lift than its priority warrants right now.