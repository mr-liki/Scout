import type { Env } from "../types";
import { corsHeaders } from "../lib/cors";

export async function handleResumeCustomize(request: Request, env: Env): Promise<Response> {
  const origin = request.headers.get("Origin");
  const headers = corsHeaders(origin, env.ALLOWED_ORIGINS);

  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405, headers });
  }

  try {
    const { resumeText, jobDescription, jobTitle } = await request.json() as {
      resumeText: string;
      jobDescription: string;
      jobTitle?: string;
    };

    if (!resumeText || resumeText.trim().length < 50) {
      return Response.json({ error: "Resume text is too short (min 50 chars)" }, { status: 400, headers });
    }
    if (!jobDescription || jobDescription.trim().length < 20) {
      return Response.json({ error: "Job description is too short (min 20 chars)" }, { status: 400, headers });
    }

    const prompt = `You are an expert resume writer and ATS (Applicant Tracking System) optimization specialist with 15 years of experience.

JOB TITLE: ${jobTitle || "Not specified"}

JOB DESCRIPTION:
${jobDescription.slice(0, 3000)}

CANDIDATE RESUME:
${resumeText.slice(0, 4000)}

Analyze the job description and the resume. Return ONLY valid JSON (no markdown, no code fences) with this exact structure:
{
  "optimized_resume": "The full tailored resume text with improvements, reworded to match the job description. Keep the same structure but optimize language, add relevant keywords naturally, and strengthen bullet points.",
  "match_score": 75,
  "missing_keywords": ["keyword1", "keyword2", "keyword3"],
  "strengths": ["strength1", "strength2"],
  "improvements": ["improvement1", "improvement2"],
  "ats_tips": ["tip1", "tip2"]
}

Rules for the optimized resume:
- Keep the original structure and sections
- Naturally incorporate missing keywords from the job description
- Use strong action verbs
- Quantify achievements where possible
- Keep it concise and professional
- Do NOT fabricate experience or skills the candidate doesn't have

Return ONLY the JSON object, no other text.`;

    const response = await env.AI.run("@cf/meta/llama-3.1-8b-instruct-fast", {
      messages: [
        { role: "system", content: "You are an expert resume writer. Return only valid JSON." },
        { role: "user", content: prompt },
      ],
      max_tokens: 2048,
      temperature: 0.3,
      stream: false,
    });

    const aiText = response?.response || "";

    // Try to parse JSON from the response
    let result: any;
    try {
      // Find the LAST complete JSON object (AI sometimes appends extra text)
      const jsonMatches = aiText.match(/\{[\s\S]*?\}/g) || [];
      let parsed: any = null;
      for (const m of jsonMatches) {
        try {
          const candidate = JSON.parse(m);
          if (candidate.optimized_resume || candidate.match_score) {
            parsed = candidate;
            break;
          }
        } catch { /* skip invalid fragments */ }
      }

      // If no good match with non-greedy, try greedy on last match
      if (!parsed) {
        const greedyMatch = aiText.match(/\{[\s\S]*\}/);
        if (greedyMatch) parsed = JSON.parse(greedyMatch[0]);
      }

      if (parsed) {
        // Flatten: if AI nests results inside optimized_resume object, extract them
        const inner = parsed.optimized_resume && typeof parsed.optimized_resume === "object"
          ? parsed.optimized_resume
          : null;
        result = {
          optimized_resume: inner?.optimized_resume || parsed.optimized_resume || "",
          match_score: inner?.match_score ?? parsed.match_score ?? 50,
          missing_keywords: inner?.missing_keywords || parsed.missing_keywords || [],
          strengths: inner?.strengths || parsed.strengths || [],
          improvements: inner?.improvements || parsed.improvements || [],
          ats_tips: inner?.ats_tips || parsed.ats_tips || [],
        };
      } else {
        throw new Error("No valid JSON found");
      }
    } catch {
      result = {
        optimized_resume: aiText,
        match_score: 50,
        missing_keywords: [],
        strengths: ["AI generated a custom resume — review the output below"],
        improvements: ["AI response was not structured JSON — review manually"],
        ats_tips: ["Ensure your resume is in a clean text format for ATS systems"],
      };
    }

    return Response.json(result, { headers });
  } catch (e: any) {
    return Response.json({ error: "Failed to customize resume", message: e.message }, { status: 500, headers });
  }
}

export async function handleResumeScore(request: Request, env: Env): Promise<Response> {
  const origin = request.headers.get("Origin");
  const headers = corsHeaders(origin, env.ALLOWED_ORIGINS);

  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405, headers });
  }

  try {
    const { resumeText, jobDescription } = await request.json() as {
      resumeText: string;
      jobDescription: string;
    };

    if (!resumeText || !jobDescription) {
      return Response.json({ error: "Both resumeText and jobDescription required" }, { status: 400, headers });
    }

    const prompt = `Score how well this resume matches the job description. Return ONLY valid JSON.

JOB DESCRIPTION:
${jobDescription.slice(0, 2000)}

RESUME:
${resumeText.slice(0, 3000)}

Return JSON:
{
  "match_score": 72,
  "keyword_match": 65,
  "experience_match": 80,
  "summary": "Brief 2-sentence summary of the match quality",
  "missing_keywords": ["kw1", "kw2", "kw3"]
}`;

    const response = await env.AI.run("@cf/meta/llama-3.1-8b-instruct-fast", {
      messages: [
        { role: "system", content: "You are an ATS scoring algorithm. Return only valid JSON." },
        { role: "user", content: prompt },
      ],
      max_tokens: 512,
      temperature: 0.1,
      stream: false,
    });

    const aiText = response?.response || "";
    let result;
    try {
      const jsonMatch = aiText.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        result = JSON.parse(jsonMatch[0]);
      } else {
        throw new Error("No JSON found");
      }
    } catch {
      result = { match_score: 50, keyword_match: 50, experience_match: 50, summary: "Could not parse AI response", missing_keywords: [] };
    }

    return Response.json(result, { headers });
  } catch (e: any) {
    return Response.json({ error: "Failed to score resume", message: e.message }, { status: 500, headers });
  }
}
