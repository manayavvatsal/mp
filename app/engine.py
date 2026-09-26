import re

from datetime import datetime

from typing import Any


def pct(x):
    try:
        return f"{abs(float(x)) * 100:.0f}%"
    except Exception:
        return str(x)


def first_name(m):
    ident = m.get("identity", {})
    return ident.get("owner_first_name") or ident.get("name", "there").split()[0]


def active_offers(m):
    return [o for o in m.get("offers", []) if o.get("status") == "active"]


def find_digest(category, trigger):
    p = trigger.get("payload", {})
    wanted = (
        p.get("top_item_id")
        or p.get("digest_item_id")
        or p.get("alert_id")
        or p.get("digest_item_id")
    )

    if not wanted:
        return None

    for d in category.get("digest", []):
        if d.get("id") == wanted:
            return d

    return None


def safe_text(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def cta_for(kind, scope):
    if kind in {
        "research_digest",
        "cde_opportunity",
        "curious_ask_due",
        "perf_spike",
        "milestone_reached",
        "category_seasonal",
    }:
        return "open_ended"

    if kind in {"auto_reply"}:
        return "none"

    return "YES/STOP" if scope == "merchant" else "YES/STOP"


def compose(
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: dict | None = None,
) -> dict:
    """Deterministic, context-grounded composer. No external data is used."""

    kind = trigger.get("kind", "")
    scope = trigger.get("scope", "merchant")
    p = trigger.get("payload", {}) or {}

    name = first_name(merchant)

    mname = merchant.get("identity", {}).get("name", "")

    cat = merchant.get("category_slug") or category.get("slug", "")

    offer = active_offers(merchant)
    offer_title = offer[0].get("title") if offer else None

    digest = find_digest(category, trigger)

    skey = trigger.get("suppression_key", trigger.get("id", kind))

    # ================================================================
    # CUSTOMER-FACING MESSAGES
    # ================================================================

    if scope == "customer":
        cname = customer.get("identity", {}).get("name", "there")
        lang = customer.get("identity", {}).get("language_pref", "english")
        pref = customer.get("preferences", {})
        slots = p.get("available_slots", [])

        if kind == "recall_due":
            slot_text = " or ".join(
                x.get("label", "")
                for x in slots[:2]
                if x.get("label")
            )

            price = offer_title or "the available cleaning offer"

            body = (
                f"Hi {cname}, {mname} here 🦷 — your "
                f"{p.get('service_due', 'cleaning')} recall is due."
            )

            if slot_text:
                body += f" We have {slot_text}."

            body += f" {price}."
            body += " Reply YES to book a slot, or STOP to opt out."

            if "hi-en" in lang.lower():
                body = (
                    f"Hi {cname}, {mname} here 🦷 — aapka "
                    f"{p.get('service_due', 'cleaning')} recall due hai."
                )

                if slot_text:
                    body += f" Available: {slot_text}."

                body += (
                    f" {price}. Reply YES to book, or STOP to opt out."
                )

        elif kind in {"wedding_package_followup", "bridal_followup"}:
            wd = p.get("wedding_date") or pref.get("wedding_date")
            days = p.get("days_to_wedding")

            body = (
                f"Hi {cname} 💍 {name} from "
                f"{merchant.get('identity', {}).get('name', 'the business')} here."
            )

            if days is not None:
                body += f" {days} days to your wedding."
            elif wd:
                body += f" Your wedding is on {wd}."

            body += " Your next bridal-prep window is open."

            if offer_title:
                body += f" {offer_title} is active."

            body += (
                " Reply YES if you want us to block a suitable slot, "
                "or STOP to opt out."
            )

        elif kind == "customer_lapsed_hard":
            days = p.get("days_since_last_visit")
            focus = p.get("previous_focus")

            body = f"Hi {cname} 👋 {name} from {mname} here."

            if days is not None:
                body += (
                    f" It’s been {days} days since your last visit — no judgment."
                )

            if focus:
                body += f" We remember your focus was {focus}."

            if offer_title:
                body += f" {offer_title} is available."

            body += (
                " Reply YES for a trial/return slot, or STOP to opt out."
            )

        elif kind == "trial_followup":
            body = (
                f"Hi {cname}, {name} from {mname} here. "
                f"Your trial was on {p.get('trial_date', 'the recent trial')}."
            )

            opts = p.get("next_session_options", [])

            if opts:
                body += f" Next option: {opts[0].get('label', '')}."

            body += " Reply YES to reserve it, or STOP to opt out."

        elif kind == "chronic_refill_due":
            meds = p.get("molecule_list", [])

            body = (
                f"Namaste {cname} — {mname} here. "
                f"Your refill for {', '.join(meds)} is due; "
                f"stock runs out on "
                f"{p.get('stock_runs_out_iso', 'the due date')[:10]}."
            )

            body += (
                " Reply YES to arrange the refill, or STOP to opt out."
            )

        else:
            body = (
                f"Hi {cname}, {mname} here. "
                f"{safe_text(kind.replace('_', ' ')).capitalize()} "
                "is due based on your saved context. "
                "Reply YES to continue, or STOP to opt out."
            )

        rationale = (
            f"Customer trigger '{kind}' matched to customer "
            "relationship/preferences and merchant context; "
            "message uses only supplied facts."
        )

        return {
            "body": safe_text(body),
            "cta": "YES/STOP",
            "send_as": "merchant_on_behalf",
            "suppression_key": skey,
            "rationale": rationale,
        }

    # ================================================================
    # MERCHANT-FACING CASES
    # ================================================================

    if kind == "research_digest" and digest:
        cohort = merchant.get(
            "customer_aggregate", {}
        ).get("high_risk_adult_count")

        body = (
            f"{name}, {digest.get('source', 'This week’s digest')} "
            f"has a relevant item: "
            f"{digest.get('title', '').rstrip('.')}."
        )

        if cohort:
            body += (
                f" You have {cohort} high-risk adult patients, "
                "so this is directly relevant to that cohort."
            )

        body += (
            " Want me to pull the source and turn it into "
            "a short patient-facing note?"
        )

        return {
            "body": safe_text(body),
            "cta": "open_ended",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "Research trigger selected because its cited digest item "
                "directly matches the merchant's category and available "
                "cohort signal."
            ),
        }

    if kind == "regulation_change" and digest:
        deadline = (
            p.get("deadline_iso")
            or trigger.get("expires_at", "")[:10]
        )

        body = (
            f"{name}, compliance update: "
            f"{digest.get('title', '')} "
            f"Deadline: {deadline}. "
            f"{digest.get('actionable', '')} "
            "Want me to turn the required checks into a short "
            "SOP checklist?"
        )

        return {
            "body": safe_text(body),
            "cta": "YES/STOP",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "High-urgency regulatory trigger paired with the cited "
                "category digest and its stated action."
            ),
        }

    if kind == "perf_dip":
        metric = p.get("metric", "metric")
        delta = p.get("delta_pct", 0)
        base = p.get("vs_baseline")

        body = (
            f"{name}, your {metric} is down "
            f"{pct(delta)} over the last "
            f"{p.get('window', '7d')} vs the supplied baseline"
        )

        if base is not None:
            body += f" of {base}"

        body += (
            ". I’d focus on the trigger behind the drop before "
            "changing offers. Want me to draft a focused recovery action?"
        )

        return {
            "body": safe_text(body),
            "cta": "YES/STOP",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "Performance-dip trigger is the strongest immediate "
                "merchant signal; message names the changed metric "
                "and avoids inventing a cause."
            ),
        }

    if kind == "renewal_due":
        plan = p.get(
            "plan",
            merchant.get("subscription", {}).get("plan", "plan"),
        )

        days_remaining = p.get(
            "days_remaining",
            merchant.get("subscription", {}).get("days_remaining", ""),
        )

        body = (
            f"{name}, your {plan} renewal is "
            f"{days_remaining} days away."
        )

        if p.get("renewal_amount") is not None:
            body += (
                f" Renewal amount in context: ₹{p['renewal_amount']}."
            )

        body += " Want me to outline the renewal next step?"

        return {
            "body": safe_text(body),
            "cta": "YES/STOP",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "Renewal deadline is explicit and time-sensitive; "
                "only supplied plan and amount are referenced."
            ),
        }

    if kind == "festival_upcoming":
        body = (
            f"{name}, {p.get('festival', 'The upcoming festival')} "
            f"is on {p.get('date', 'the supplied date')} "
            f"({p.get('days_until', '')} days away)."
        )

        if offer_title:
            body += f" Your active offer is {offer_title}."

        body += (
            " Want me to turn this into one concrete seasonal post "
            "using the offer already on your account?"
        )

        return {
            "body": safe_text(body),
            "cta": "open_ended",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "Seasonal trigger is paired with the merchant's actual "
                "active offer rather than an invented promotion."
            ),
        }

    # ================================================================
    # IMPROVED: CURIOUS ASK
    # ================================================================

    if kind == "curious_ask_due":
        asked_for = (
            p.get("service")
            or p.get("service_name")
            or p.get("top_service")
            or p.get("focus")
        )

        window = (
            p.get("window")
            or p.get("period")
            or "this week"
        )

        count = (
            p.get("count")
            or p.get("occurrences")
            or p.get("mentions")
        )

        if asked_for and count is not None:
            body = (
                f"Hi {name}! {asked_for} has come up {count} times "
                f"in the supplied {window} signal at {mname}."
            )

            body += (
                " Want me to turn that signal into a short "
                "customer-facing post?"
            )

        elif asked_for:
            body = (
                f"Hi {name}! {asked_for} is the service highlighted "
                f"in the supplied {window} signal for {mname}."
            )

            body += (
                " Want me to turn that signal into a short "
                "customer-facing post?"
            )

        else:
            body = (
                f"Hi {name}! I have a fresh {window} signal for {mname}, "
                "but the supplied context does not identify the service."
            )

            body += (
                " Which service should I turn into a short "
                "customer-facing post?"
            )

        return {
            "body": safe_text(body),
            "cta": "open_ended",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "Curious-ask trigger is handled using only service, "
                "timing, and count fields actually present in the "
                "supplied trigger; missing service data is not invented."
            ),
        }

    if kind == "winback_eligible":
        days_since_expiry = p.get(
            "days_since_expiry",
            merchant.get("subscription", {}).get(
                "days_since_expiry", ""
            ),
        )

        body = (
            f"{name}, {days_since_expiry} days since expiry "
            f"and performance is down "
            f"{pct(p.get('perf_dip_pct', 0))}."
        )

        if p.get("lapsed_customers_added_since_expiry") is not None:
            body += (
                f" You also have "
                f"{p['lapsed_customers_added_since_expiry']} "
                "lapsed customers added since expiry."
            )

        body += " Want me to draft a focused win-back message?"

        return {
            "body": safe_text(body),
            "cta": "YES/STOP",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "Win-back trigger combines explicit expiry and "
                "performance/customer counts to make the next "
                "action concrete."
            ),
        }

    if kind == "ipl_match_today":
        match = p.get("match", "today’s match")

        body = (
            f"Quick heads-up {name} — {match} at "
            f"{p.get('venue', 'the supplied venue')} tonight."
        )

        if offer_title:
            body += (
                f" Your active offer is already {offer_title}; "
                "I’d reuse it rather than inventing a match promo."
            )

        body += " Want me to draft the delivery-first copy?"

        return {
            "body": safe_text(body),
            "cta": "open_ended",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "Match-day trigger is handled with the merchant's "
                "existing offer and no unsupported demand statistic."
            ),
        }

    if kind == "review_theme_emerged":
        occurrences = p.get("occurrences_30d", 1)
        theme = p.get("theme", "the same theme")

        body = (
            f"{name}, {occurrences} reviews in the last 30 days "
            f"mention {theme}"
        )

        if p.get("trend"):
            body += f" and the trend is {p['trend']}"

        body += (
            ". Want me to draft one concrete response/process change?"
        )

        return {
            "body": safe_text(body),
            "cta": "YES/STOP",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "Emerging review theme is the direct signal; "
                "message uses its count/trend and proposes one "
                "focused response."
            ),
        }

    if kind == "milestone_reached":
        if (
            p.get("value_now") is not None
            and p.get("milestone_value") is not None
        ):
            body = (
                f"{name}, you’re at {p['value_now']} "
                f"{p.get('metric', 'milestone')} — "
                f"{p['milestone_value']} is the next milestone."
            )
        else:
            body = (
                f"{name}, a milestone trigger is active for {mname}."
            )

        body += (
            " Want me to draft a simple post around the milestone "
            "without adding a new offer?"
        )

        return {
            "body": safe_text(body),
            "cta": "open_ended",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "Milestone trigger provides a concrete progress "
                "marker and a low-effort follow-on."
            ),
        }

    if kind == "active_planning_intent":
        topic = p.get("intent_topic", "the requested plan")
        last = p.get("merchant_last_message")

        body = (
            f"{name}, here’s a starter structure for "
            f"{topic.replace('_', ' ')}."
        )

        if last:
            body += f" You asked: “{last}”."

        body += (
            " I can turn the idea into a concrete draft using only "
            "the offers, locality and constraints already in your context."
        )

        return {
            "body": safe_text(body),
            "cta": "open_ended",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "Active planning indicates the merchant is already "
                "asking for execution; response advances the request "
                "instead of qualifying again."
            ),
        }

    if kind == "seasonal_perf_dip":
        body = (
            f"{name}, {p.get('metric', 'performance')} is down "
            f"{pct(p.get('delta_pct', 0))} over "
            f"{p.get('window', '7d')}, and the supplied context "
            f"marks this as expected seasonal behavior "
            f"({p.get('season_note', 'seasonal window')})."
        )

        body += (
            " I’d avoid reacting with unsupported claims; focus on "
            "retention during the stated lull. Want a retention-action draft?"
        )

        return {
            "body": safe_text(body),
            "cta": "YES/STOP",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "The trigger explicitly marks the dip as expected; "
                "the recommendation reframes rather than fabricates "
                "a cause or benchmark."
            ),
        }

    if kind == "supply_alert":
        batches = p.get("affected_batches", [])

        affected = merchant.get(
            "customer_aggregate", {}
        ).get("chronic_rx_count")

        body = (
            f"{name}, supply alert for "
            f"{p.get('molecule', 'the supplied molecule')}: "
            f"affected batches {', '.join(batches)} by "
            f"{p.get('manufacturer', 'the supplied manufacturer')}."
        )

        if affected is not None:
            body += (
                f" Your context lists {affected} chronic-Rx customers."
            )

        body += (
            " Want me to draft the customer notification "
            "and replacement workflow?"
        )

        return {
            "body": safe_text(body),
            "cta": "YES/STOP",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "Compliance/supply trigger is high urgency; "
                "batch identifiers are reproduced exactly and no "
                "unprovided affected-customer count is invented."
            ),
        }

    if kind == "category_seasonal":
        trends = p.get("trends", [])

        body = (
            f"{name}, summer demand has shifted in the supplied signal: "
            f"{', '.join(trends[:3])}."
        )

        body += (
            " The trigger recommends a shelf action; want me to turn "
            "that into a short priority list using only this signal?"
        )

        return {
            "body": safe_text(body),
            "cta": "open_ended",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "Category-seasonal trigger is summarized directly "
                "and tied to its explicit shelf-action recommendation."
            ),
        }

    if kind == "gbp_unverified":
        body = (
            f"{name}, your GBP is currently marked unverified "
            "in the supplied context."
        )

        if p.get("estimated_uplift_pct") is not None:
            body += (
                f" The context estimates up to "
                f"{pct(p['estimated_uplift_pct'])} uplift "
                "from verification."
            )

        body += " Want the verification path summarized?"

        return {
            "body": safe_text(body),
            "cta": "open_ended",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "Verification status is directly provided; "
                "any uplift is explicitly attributed to the "
                "supplied context."
            ),
        }

    if kind == "cde_opportunity" and digest:
        body = (
            f"{name}, {digest.get('title', '')} — "
            f"{digest.get('date', 'the scheduled date')}."
        )

        if digest.get("credits") is not None:
            body += f" {digest['credits']} credits"

        if digest.get("summary"):
            body += f" {digest['summary']}"

        body += (
            " Want me to pull the registration details "
            "from the supplied context?"
        )

        return {
            "body": safe_text(body),
            "cta": "open_ended",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "CDE trigger points to a specific category digest "
                "item; message cites its supplied date/credits/summary."
            ),
        }

    # ================================================================
    # IMPROVED: COMPETITOR OPENED
    # ================================================================

    if kind == "competitor_opened":
        distance = p.get("distance_km")
        competitor = p.get("competitor_name")
        their_offer = p.get("their_offer")
        category_name = p.get("category")
        opened_date = p.get("opened_date") or p.get("date")

        body = f"{name}, a new competitor is listed"

        if competitor:
            body += f": {competitor}"

        if distance is not None:
            body += f", {distance} km away"

        if category_name:
            body += f" in the {category_name} category"

        if opened_date:
            body += f", listed on {opened_date}"

        if their_offer:
            body += f". Their listed offer is {their_offer}"

        body += (
            ". Want me to compare this with your active offer "
            "without changing anything yet?"
        )

        return {
            "body": safe_text(body),
            "cta": "open_ended",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "Competitor trigger is grounded in supplied competitor "
                "identity, distance, category, date, and offer fields. "
                "The response proposes comparison without assuming "
                "competitive impact."
            ),
        }

    if kind == "perf_spike":
        metric = p.get("metric", "performance")
        delta = p.get("delta_pct")

        body = (
            f"{name}, {metric} has a positive performance signal"
        )

        if delta is not None:
            body += (
                f" ({pct(delta)} over "
                f"{p.get('window', '7d')})"
            )

        if p.get("vs_baseline") is not None:
            body += f" vs baseline {p['vs_baseline']}"

        body += "."

        if p.get("likely_driver"):
            body += (
                f" The supplied signal points to "
                f"{p['likely_driver']}."
            )

        body += (
            " Want me to turn the signal into one follow-up action?"
        )

        return {
            "body": safe_text(body),
            "cta": "open_ended",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "Positive performance trigger is grounded in the "
                "provided delta/baseline and only uses an explicitly "
                "supplied likely driver."
            ),
        }

    # ================================================================
    # IMPROVED: DORMANT WITH VERA
    # ================================================================

    if kind == "dormant_with_vera":
        days = p.get("days_since_last_merchant_message")

        if days is None:
            days = merchant.get(
                "subscription", {}
            ).get("days_since_expiry")

        last_topic = p.get("last_topic")
        last_message = p.get("merchant_last_message")

        if days is not None:
            body = (
                f"{name}, it’s been {days} days since "
                "the last merchant message"
            )
        else:
            body = (
                f"{name}, the supplied context shows "
                "a dormant merchant conversation"
            )

        if last_topic:
            body += f". The last topic was {last_topic}"
        elif last_message:
            body += (
                f'. The last message was "{safe_text(last_message)}"'
            )

        body += (
            ". If useful, I can pick up from that context "
            "with one concrete next step."
        )

        return {
            "body": safe_text(body),
            "cta": "open_ended",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "Dormancy trigger is grounded in the supplied "
                "inactivity period and the most recent conversation "
                "context when available."
            ),
        }

    # ================================================================
    # IMPROVED: CUSTOMER LAPSED SOFT
    # ================================================================

    if kind == "customer_lapsed_soft":
        days = (
            p.get("days_since_last_visit")
            or p.get("days_since_last_order")
            or p.get("days_lapsed")
        )

        customer_count = (
            p.get("customer_count")
            or p.get("lapsed_customer_count")
            or p.get("customers_affected")
        )

        focus = (
            p.get("previous_focus")
            or p.get("service")
            or p.get("category")
        )

        body = (
            f"{name}, a customer recall/win-back window has opened"
        )

        if days is not None:
            body += (
                f" after {days} days since the relevant last activity"
            )

        if customer_count is not None:
            body += f" for {customer_count} customer(s)"

        if focus:
            body += f", with {focus} as the supplied focus"

        body += (
            ". Want me to prepare a context-grounded outreach draft?"
        )

        return {
            "body": safe_text(body),
            "cta": "YES/STOP",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "Customer-lapse trigger is made specific using only "
                "supplied lapse timing, affected-customer count, and "
                "focus fields; no customer details are invented."
            ),
        }

    # ================================================================
    # IMPROVED: APPOINTMENT TOMORROW
    # ================================================================

    if kind == "appointment_tomorrow":
        appointment_date = (
            p.get("appointment_date")
            or p.get("date")
            or p.get("appointment_date_iso")
        )

        appointment_time = (
            p.get("appointment_time")
            or p.get("time")
            or p.get("appointment_time_iso")
        )

        service = (
            p.get("service")
            or p.get("service_name")
        )

        customer_name = p.get("customer_name")

        body = f"{name}, there’s an appointment tomorrow"

        if customer_name:
            body += f" for {customer_name}"

        if service:
            body += f" for {service}"

        if appointment_date:
            body += f" on {appointment_date}"

        if appointment_time:
            body += f" at {appointment_time}"

        body += (
            " in the supplied trigger context. "
            "Want me to prepare the reminder copy?"
        )

        return {
            "body": safe_text(body),
            "cta": "YES/STOP",
            "send_as": "vera",
            "suppression_key": skey,
            "rationale": (
                "Appointment trigger is grounded in the supplied "
                "appointment date, time, service, and customer fields "
                "when available."
            ),
        }

    # ================================================================
    # IMPROVED GENERIC FALLBACK
    # ================================================================

    signal_parts = []

    preferred_fields = [
        ("metric", "metric"),
        ("delta_pct", "change"),
        ("window", "window"),
        ("days_remaining", "days remaining"),
        ("days_since_expiry", "days since expiry"),
        ("days_since_last_visit", "days since last visit"),
        ("service", "service"),
        ("service_name", "service"),
        ("product", "product"),
        ("molecule", "molecule"),
        ("festival", "festival"),
        ("date", "date"),
        ("competitor_name", "competitor"),
        ("distance_km", "distance"),
    ]

    seen_labels = set()

    for field_name, label in preferred_fields:
        value = p.get(field_name)

        if value is None or value == "":
            continue

        if label in seen_labels:
            continue

        if field_name == "delta_pct":
            formatted = pct(value)
            signal_parts.append(f"{label}: {formatted}")

        elif field_name == "distance_km":
            signal_parts.append(f"{label}: {value} km")

        else:
            signal_parts.append(
                f"{label}: {safe_text(value)}"
            )

        seen_labels.add(label)

        if len(signal_parts) >= 3:
            break

    trigger_name = safe_text(
        kind.replace("_", " ")
    ).capitalize()

    body = (
        f"{name}, {trigger_name} is active for {mname}."
    )

    if signal_parts:
        body += (
            " Supplied signal: "
            + "; ".join(signal_parts)
            + "."
        )

    body += (
        " Want me to turn this signal into one concrete next step?"
    )

    return {
        "body": safe_text(body),
        "cta": cta_for(kind, scope),
        "send_as": "vera",
        "suppression_key": skey,
        "rationale": (
            f"Fallback composition is grounded in trigger kind "
            f"'{kind}', merchant identity, and up to three supplied "
            "trigger fields; no missing facts are inferred."
        ),
    }