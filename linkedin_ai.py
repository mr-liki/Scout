#!/usr/bin/env python3
"""
linkedin_ai.py - Free versions of LinkedIn Premium's AI features.

LinkedIn Premium ($29.99/month) includes:
  1. AI-powered job discovery from plain-language career goals
  2. AI suggestions for headline / about / experience sections
  3. AI-drafted InMail / connection messages

CADDY provides the same functionality for free:

  - When HF_API_KEY is set (or api-inference.huggingface.co is reachable),
    a real instruct model (Mistral-7B-Instruct) generates the content.
  - Otherwise a smart OFFLINE template engine produces professional,
    ready-to-use drafts — no API key, no internet needed.

Design: every public method tries AI first, and gracefully falls back to the
offline engine if the network/model is unavailable. Nothing ever crashes.
"""

import os
import re
import requests

# Hugging Face instruct model (free tier). Swap for any other instruct model.
HF_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"
HF_URL = f"https://api-inference.huggingface.co/models/{HF_MODEL}"


def _clean(text):
    """Collapse whitespace and strip quotes/artifacts the model may leave."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace('"', "").replace("```", "")
    return text.strip('"\n ')


class LinkedInAI:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("HF_API_KEY")
        # Session latch: once HF is unreachable we stop trying, so AI commands
        # never hang on a dead host — the offline engine takes over instantly.
        self.ai_available = True
        self._probed = False

    # ------------------------------------------------------------------ AI
    def generate(self, system_prompt, user_prompt, max_new_tokens=350):
        """Try the HF instruct model. Returns text or '' if unavailable."""
        if not self.ai_available:
            return ""
        try:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            payload = {
                "inputs": f"{system_prompt}\n\nUSER: {user_prompt}\nASSISTANT:",
                "parameters": {
                    "max_new_tokens": max_new_tokens,
                    "temperature": 0.7,
                    "do_sample": True,
                },
            }
            resp = requests.post(HF_URL, headers=headers, json=payload, timeout=10)
            if resp.status_code != 200:
                # 503 = model still loading (transient, retry later).
                # 401/403 = bad key (permanent for this session).
                if resp.status_code in (401, 403) and not self._probed:
                    self._probed = True
                    self.ai_available = False
                return ""
            self._probed = True
            self.ai_available = True
            data = resp.json()
            if isinstance(data, list) and data:
                text = data[0].get("generated_text", "")
                # Strip the echoed prompt
                if "ASSISTANT:" in text:
                    text = text.split("ASSISTANT:", 1)[1]
                return _clean(text)
        except Exception:
            if not self._probed:
                self._probed = True
                self.ai_available = False
        return ""

    def ai_first(self, system_prompt, user_prompt, fallback):
        """Return AI output if available, otherwise the offline fallback."""
        text = self.generate(system_prompt, user_prompt)
        return text if text else fallback

    # ------------------------------------------------------------ Headline
    def suggest_headline(self, role, years="", skills="", location="", target="", count=3):
        """3 ready-to-use LinkedIn headlines."""
        years = years or "X"
        skills = skills or "your key skills"
        location = location or "your target location"
        target = target or "roles"

        # --- Offline template engine (always works) ---
        def _article(word):
            return "an" if re.match(r"^(a|e|i|o|u)", word.lower()) else "a"

        def _tpl():
            y = re.sub(r"\s*years?", "", years.strip(), flags=re.I) if years else "X"
            role_a = f"{_article(role)} {role}" if role else role
            variants = [
                f"{role} | {y}+ Years | {skills} | {location}",
                f"{role} | {skills} | Open to {target} opportunities",
                f"Building better {skills} solutions as {role_a} | {y}+ yrs experience",
                f"{role} — {skills}. {y}+ years turning ideas into results.",
            ]
            return "\n".join(f"{i+1}. {v}" for i, v in enumerate(variants[:count]))

        system = (
            "You are an expert LinkedIn profile writer. Write concise, keyword-rich "
            "LinkedIn headlines for a job seeker. Return ONLY numbered headlines, "
            "one per line, no commentary."
        )
        user = f"Role: {role}\nYears experience: {years}\nKey skills: {skills}\nLocation: {location}\nTarget roles: {target}\n\nWrite {count} LinkedIn headlines."
        return self.ai_first(system, user, _tpl())

    # ------------------------------------------------------------- About
    def suggest_about(self, role, years="", skills="", achievements="", tone="professional", count=3):
        """3 drafts for the About section."""
        achievements = achievements or "delivered impactful results"
        skills = skills or "your core skills"
        tone = tone or "professional"

        # Grammar helpers: "an AI Engineer", "5 years of experience" (no doubles)
        def _article(word):
            return "an" if re.match(r"^(a|e|i|o|u)", word.lower()) else "a"
        role_clean = re.sub(r"\s+years?\s*$", "", role.strip(), flags=re.I)
        role_phrase = f"{_article(role_clean)} {role_clean}" if role_clean and role_clean.lower() not in ("your role",) else role_clean
        # years may arrive as "5" or "5 years" - normalize to avoid doubles
        years_num = re.sub(r"[^0-9.]", "", str(years)) if years else ""
        years_txt = f"{years_num} years" if years_num else "X years"

        def _tpl():
            variants = [
                f"With {years_txt} of experience as {role_phrase}, I specialize in {skills}. "
                f"I've {achievements}, and I bring the same energy to every challenge. "
                f"Currently exploring new opportunities where I can make an impact.",
                f"I'm {role_phrase} who believes great work comes from {skills}. "
                f"Over the last {years_txt} I've {achievements}. "
                f"Let's connect if you're looking for someone who delivers.",
                f"{role_clean} focused on {skills}. My track record: {achievements}. "
                f"Open to collaborations, mentorship, and the right next role.",
            ]
            return "\n".join(f"{i+1}. {v}" for i, v in enumerate(variants[:count]))

        system = (
            "You are an expert LinkedIn profile writer. Write professional, first-person "
            "About sections for a job seeker. Keep each draft 3-4 sentences, no fluff. "
            "Return ONLY numbered drafts, no commentary."
        )
        user = f"Role: {role}\nYears: {years}\nSkills: {skills}\nAchievements: {achievements}\nTone: {tone}\n\nWrite {count} About section drafts."
        return self.ai_first(system, user, _tpl())

    # --------------------------------------------------------- Experience
    def suggest_experience(self, role, bullet_points="", count=3):
        """Turn rough achievements into polished experience bullet points."""
        bullet_points = bullet_points or "a project that improved a key metric"

        # Strip a leading action verb the user may have included (e.g.
        # "led team..." -> "team...") so the template verb isn't doubled.
        raw = bullet_points.strip()
        first = raw.split(" ")[0].lower().rstrip(",s")
        if first in ("led", "lead", "built", "created", "developed", "improved",
                     "managed", "owned", "spearheaded", "designed", "implemented",
                     "delivered", "launched", "drove", "worked", "helped", "made"):
            raw = raw.split(" ", 1)[1] if " " in raw else raw

        def _tpl():
            # Turn the user's rough note into STAR-ish bullets
            variants = [
                f"Led {raw}, delivering measurable improvements to team outcomes.",
                f"Owned {raw} end-to-end, collaborating across teams to ship on time.",
                f"Improved {raw}, using data to drive decisions and iterate quickly.",
                f"Spearheaded {raw}, recognized for consistency and quality.",
            ]
            return "\n".join(f"• {v}" for v in variants[:count])

        system = (
            "You are a resume-writing expert. Turn the user's rough notes into strong, "
            "action-oriented bullet points for a LinkedIn Experience section. Start each "
            "bullet with a strong verb. Return ONLY bullets, one per line."
        )
        user = f"Role: {role}\nRough notes: {bullet_points}\n\nWrite {count} polished bullet points."
        return self.ai_first(system, user, _tpl())

    # ---------------------------------------------------- Connection msg
    def draft_connection_message(self, recipient_name="", company="", reason="", count=3):
        """Personalized InMail / connection request drafts."""
        recipient_name = recipient_name or "there"
        company = company or "your company"
        reason = reason or "your impressive work in this field"

        # Normalize the reason so grammar stays clean:
        # "liked your ML talk" -> "your ML talk" (the template supplies the verb)
        reason_clean = reason.strip().strip('.,')
        low = reason_clean.lower()
        for prefix in ("i liked ", "i loved ", "liked ", "loved ", "admired ",
                       "i admired ", "impressed by ", "impressed with ", "i was impressed by "):
            if low.startswith(prefix):
                reason_clean = reason_clean[len(prefix):].strip()
                break
        if not reason_clean:
            reason_clean = "your work in this field"
        # Fix acronym casing mid-sentence: "ml" / "ai" -> "ML" / "AI"
        reason_clean = re.sub(r"\bml\b", "ML", reason_clean)
        reason_clean = re.sub(r"\bai\b", "AI", reason_clean)
        reason_lower = reason_clean.lower()

        def _tpl():
            variants = [
                f"Hi {recipient_name}, I came across your work at {company} and was impressed by {reason_clean}. "
                f"I'd love to connect and learn more about your journey.",
                f"Hi {recipient_name}, I'm currently exploring opportunities and {reason_lower} really stood out to me. "
                f"Would be great to connect — happy to share how my background could help at {company}.",
                f"Hello {recipient_name}, as someone interested in {reason_lower}, I'd value the chance to connect "
                f"with you and hear about your experience at {company}.",
            ]
            return "\n".join(f"{i+1}. {v}" for i, v in enumerate(variants[:count]))

        system = (
            "You are an expert at writing LinkedIn connection requests and InMails. "
            "Write short, genuine, personalized messages that avoid sounding robotic or "
            "salesy. Max 3 sentences each. Return ONLY numbered messages, no commentary."
        )
        user = f"Recipient: {recipient_name}\nCompany: {company}\nReason for connecting: {reason}\n\nWrite {count} connection messages."
        return self.ai_first(system, user, _tpl())

    # ---------------------------------------------------- Job discovery
    def discover_jobs(self, career_goal, max_results=5):
        """
        Premium-style AI job discovery: turn a plain-language career goal into
        a ranked list of matching jobs.

        career_goal examples:
          - "I'm a Python developer with 3 years of experience looking for remote work"
          - "Data scientist in Bengaluru, 2 years experience"
        """
        keywords, location = self._parse_goal(career_goal)
        if not keywords:
            return "I couldn't find job keywords in that description. Try: 'Python developer with 3 years experience looking for remote ML roles'"

        from linkedin_rss_tracker import LinkedInRSSTracker
        tracker = LinkedInRSSTracker()
        jobs = tracker.search_jobs(keywords, location, early_only=False)

        if not jobs:
            return (f"🔍 Parsed your goal as '{keywords}'" + (f" in {location}" if location else "") +
                    ", but no jobs came back right now. Try rephrasing or broadening the goal.")

        # Rank: early-applicant (low competition) first, then recent
        jobs.sort(key=lambda j: (j.get("early_applicant", False), ), reverse=True)

        result = (f"🎯 AI JOB DISCOVERY\n"
                  f"Goal understood: '{_clean(career_goal)}'\n"
                  f"Searching: {keywords}" + (f" in {location}" if location else "") + "\n\n")
        shown = 0
        for job in jobs:
            if shown >= max_results:
                break
            title = job.get("title", "N/A")
            company = job.get("company", "N/A")
            loc = job.get("location", "")
            link = job.get("link") or job.get("url", "")
            badge = " 🔥 EARLY APPLICANT" if job.get("early_applicant") else ""
            result += f"• {title} @ {company}{badge}\n"
            if loc:
                result += f"  📍 {loc}\n"
            if link:
                result += f"  🔗 {link}\n"
            result += "\n"
            shown += 1
        result += f"💡 Found {len(jobs)} matches — top {shown} shown. Type 'Python Developer early applicants' for even lower competition."
        return result

    def _parse_goal(self, goal):
        """Extract (keywords, location) from a plain-language career goal."""
        goal = goal.lower().strip()
        # Strip goal-y filler phrases (word-boundary aware so single letters
        # like "a" don't destroy words, e.g. "data scientist" stays intact)
        phrases = ["looking for", "i want to be", "i want to", "i'd like to", "i would like to",
                   "i'm looking for", "i am looking for", "i'm interested in", "i am interested in",
                   "i have experience in", "with experience", "years of experience", "years experience",
                   "find me", "discover", "recommend", "suggest", "career", "goal",
                   "know", "using", "skilled in", "experienced in", "work as", "want to be",
                   "to be", "to work", "work", "job", "jobs", "role", "roles", "position",
                   "positions", "opportunity", "opportunities"]
        for phrase in phrases:
            goal = re.sub(r"\b" + re.escape(phrase) + r"\b", " ", goal)
        # Single-word fillers, also word-boundary
        for w in ["i", "am", "a", "an", "my", "me", "with"]:
            goal = re.sub(r"\b" + w + r"\b", " ", goal)

        # Location: "in X" or "at X" (mid-sentence or trailing)
        location = ""
        m = re.search(r"\b(?:in|at|based in|near)\s+([a-z\s,]+?)\s*(?:,|$)", goal)
        if m:
            cand = m.group(1).strip().rstrip(",")
            # Only treat as location if it doesn't look like a skill keyword
            if len(cand.split()) <= 4:
                # Drop a leading "the" (e.g. "in the United States")
                cand = re.sub(r"^the\s+", "", cand)
                location = " ".join(w.capitalize() for w in cand.split())
                goal = goal[: m.start()] + " " + goal[m.end():]

        # Keep the meaningful words (drop generic filler)
        filler = {"a", "an", "the", "and", "or", "of", "to", "for", "with", "on", "in",
                  "at", "by", "as", "is", "am", "i", "me", "my", "we", "work", "working",
                  "remote", "remote-first", "hyrbid", "hybrid", "new", "good", "great", "best",
                  "know", "using", "want", "be", "looking"}
        # Keep only meaningful words; drop standalone numbers ("3 years" -> skip "3")
        words = [w for w in re.split(r"\W+", goal)
                 if w and w not in filler and not w.isdigit()]
        # Nicer casing for well-known terms
        def _cap(w):
            return "AI" if w.lower() == "ai" else ("ML" if w.lower() == "ml" else w.capitalize())
        keywords = " ".join(_cap(w) for w in words[:4]) if words else ""
        return keywords, location
