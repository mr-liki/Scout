/**
 * demo.js — Sample dataset + a tiny local search engine.
 *
 * When the live API isn't reachable (e.g. GitHub Pages, or the backend is
 * down), CADDY Jobs falls back to this curated dataset so the site always
 * demonstrates the full experience.
 */

const DEMO_JOBS = [
  { id: "d1", title: "Senior Python Developer", company: "Nebula Systems", location: "Remote", salary: "$120k – $160k", source: "LinkedIn", posted_date: "2026-08-07", early_applicant: true, easy_apply: false, remote: true, description: "Build high-scale Python services for our data platform. 5+ years with Django/FastAPI, PostgreSQL, and cloud infrastructure. Own features end-to-end in a small, senior team." },
  { id: "d2", title: "Backend Engineer", company: "Cloudforge", location: "Bengaluru", salary: "₹25L – ₹40L", source: "Wellfound", posted_date: "2026-08-08", early_applicant: false, easy_apply: false, remote: false, description: "Early-stage startup building developer tooling. Strong Python/Go, distributed systems, and a bias for shipping. Equity included." },
  { id: "d3", title: "Data Scientist", company: "Meridian Labs", location: "San Francisco, CA", salary: "$140k – $180k", source: "Glassdoor", posted_date: "2026-08-06", early_applicant: false, easy_apply: true, remote: false, description: "ML modeling on user-behavior data. Python, scikit-learn, PyTorch. Collaborate with product and engineering to ship models to production." },
  { id: "d4", title: "Full Stack Developer", company: "Brightpath", location: "New York, NY", salary: "$110k – $140k", source: "Indeed", posted_date: "2026-08-05", early_applicant: false, easy_apply: true, remote: false, description: "React + Node + PostgreSQL. Own features across the stack for our healthcare SaaS product. 3+ years experience." },
  { id: "d5", title: "Machine Learning Engineer", company: "Aurora AI", location: "Remote", salary: "$150k – $200k", source: "LinkedIn", posted_date: "2026-08-07", early_applicant: true, easy_apply: false, remote: true, description: "Production ML infrastructure: training pipelines, model serving, observability. PyTorch, Ray, Kubernetes." },
  { id: "d6", title: "DevOps Engineer", company: "CoreStack", location: "Pune", salary: "₹18L – ₹28L", source: "Wellfound", posted_date: "2026-08-04", early_applicant: false, easy_apply: false, remote: false, description: "Own CI/CD, cloud cost, and reliability for a fast-growing fintech. Terraform, AWS, Kubernetes. Series B startup." },
  { id: "d7", title: "Software Engineer, Frontend", company: "Pixelshift", location: "Austin, TX", salary: "$105k – $135k", source: "Glassdoor", posted_date: "2026-08-08", early_applicant: false, easy_apply: true, remote: false, description: "Design systems and product UI in React + TypeScript. Strong eye for detail, accessible by default." },
  { id: "d8", title: "QA Automation Engineer", company: "Testly", location: "Bengaluru", salary: "₹10L – ₹16L", source: "Indeed", posted_date: "2026-08-03", early_applicant: false, easy_apply: false, remote: false, description: "Build and maintain automated test suites. Python/Selenium. 2+ years QA experience, strong in CI pipelines." },
  { id: "d9", title: "AI Engineer", company: "Synapse Labs", location: "Remote", salary: "$130k – $170k", source: "LinkedIn", posted_date: "2026-08-06", early_applicant: true, easy_apply: false, remote: true, description: "LLM-powered products: RAG pipelines, prompt engineering, evaluation. Python, LangChain, vector databases." },
  { id: "d10", title: "Product Manager", company: "Foundry", location: "Remote", salary: "$120k – $150k", source: "Wellfound", posted_date: "2026-08-05", early_applicant: false, easy_apply: false, remote: true, description: "Own roadmap for our developer platform. Technical background preferred. Seed-stage, big equity." },
  { id: "d11", title: "Data Analyst", company: "Insightful", location: "Hyderabad", salary: "₹8L – ₹14L", source: "Glassdoor", posted_date: "2026-08-02", early_applicant: false, easy_apply: true, remote: false, description: "SQL + Python analytics on business data. Build dashboards, run experiments, present to stakeholders." },
  { id: "d12", title: "Site Reliability Engineer", company: "Falcon Cloud", location: "Remote", salary: "$135k – $175k", source: "Indeed", posted_date: "2026-08-07", early_applicant: false, easy_apply: false, remote: true, description: "Keep a 99.99% platform running. Kubernetes, Prometheus, incident response. On-call rotation with generous comp." },
];

/** Naive keyword/location matcher over the demo set. */
export function demoSearch(keywords, location = "") {
  const kws = keywords.toLowerCase().split(/\s+/).filter(Boolean);
  const loc = location.toLowerCase().trim();
  let jobs = DEMO_JOBS.filter((j) => {
    const hay = `${j.title} ${j.company} ${j.salary}`.toLowerCase();
    const kMatch = kws.length === 0 || kws.every((k) => hay.includes(k));
    const lMatch = !loc || j.location.toLowerCase().includes(loc) || j.remote;
    return kMatch && lMatch;
  });
  const platforms = {};
  for (const j of jobs) platforms[j.source] = (platforms[j.source] || 0) + 1;
  return {
    query: { keywords, location },
    total: jobs.length,
    platforms,
    jobs,
    errors: [],
    demo: true,
    searched_at: new Date().toISOString(),
  };
}

export function demoHealth() {
  return { status: "ok", service: "CADDY Jobs", platforms: ["LinkedIn", "Indeed", "Glassdoor", "Wellfound"], version: "1.0.0" };
}
