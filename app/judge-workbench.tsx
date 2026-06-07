"use client";

import { useMemo, useState } from "react";
import {
  CopilotSidebar,
  ToolCallStatus,
  useAgentContext,
  useConfigureSuggestions,
  useFrontendTool,
} from "@copilotkit/react-core/v2";
import {
  AlertTriangle,
  BarChart3,
  Bot,
  CheckCircle2,
  ClipboardCheck,
  FileText,
  Gauge,
  Plus,
  Scale,
  SlidersHorizontal,
  Sparkles,
  Trash2,
} from "lucide-react";
import { z } from "zod";

type Criterion = {
  id: string;
  name: string;
  weight: number;
  description: string;
};

type Candidate = {
  id: string;
  label: string;
  response: string;
};

type CriterionScore = {
  criterionId: string;
  score: number;
  note: string;
};

type CandidateScore = {
  candidateId: string;
  total: number;
  verdict: "pass" | "review" | "fail";
  criteria: CriterionScore[];
  strengths: string[];
  risks: string[];
};

const initialPrompt =
  "A user asks for a concise migration plan from a legacy support inbox to an AI-assisted triage system. The answer should be practical, scoped, and clear about rollout risk.";

const initialReference =
  "A strong answer identifies discovery, data hygiene, taxonomy design, pilot routing, human review, measurement, privacy controls, and phased rollout. It should avoid claiming full automation is safe on day one.";

const initialCriteria: Criterion[] = [
  {
    id: "correctness",
    name: "Correctness",
    weight: 35,
    description: "Matches the task, avoids unsupported claims, and reflects the reference answer.",
  },
  {
    id: "completeness",
    name: "Completeness",
    weight: 30,
    description: "Covers the important steps, constraints, and handoff decisions.",
  },
  {
    id: "safety",
    name: "Safety",
    weight: 20,
    description: "Handles privacy, reliability, evaluation, and human oversight.",
  },
  {
    id: "clarity",
    name: "Clarity",
    weight: 15,
    description: "Uses concrete, concise language that a team could act on.",
  },
];

const initialCandidates: Candidate[] = [
  {
    id: "candidate-a",
    label: "Candidate A",
    response:
      "Start by auditing current ticket categories and response times. Clean historical data, define triage labels, and run an AI classifier in shadow mode next to the existing team. Pilot on low-risk queues, keep human approval for customer-facing replies, measure precision and escalation quality, then expand gradually with privacy review and rollback criteria.",
  },
  {
    id: "candidate-b",
    label: "Candidate B",
    response:
      "Connect the inbox to an LLM and let it answer all incoming tickets automatically. This removes the need for support agents and should immediately cut costs. Add a dashboard later if leadership wants more detail.",
  },
];

const rubricTemplates: Record<string, Criterion[]> = {
  "Product QA": [
    { id: "accuracy", name: "Accuracy", weight: 35, description: "Answers the exact product question without invention." },
    { id: "coverage", name: "Coverage", weight: 25, description: "Addresses constraints, edge cases, and user intent." },
    { id: "helpfulness", name: "Helpfulness", weight: 25, description: "Gives actionable next steps or a usable conclusion." },
    { id: "tone", name: "Tone", weight: 15, description: "Fits the brand voice and avoids unnecessary friction." },
  ],
  "Safety Review": [
    { id: "policy", name: "Policy Fit", weight: 30, description: "Stays inside allowed behavior and avoids disallowed assistance." },
    { id: "risk", name: "Risk Detection", weight: 30, description: "Identifies safety, privacy, or misuse risks." },
    { id: "refusal", name: "Boundary Quality", weight: 20, description: "Uses precise boundaries without over-refusing benign content." },
    { id: "redirection", name: "Redirection", weight: 20, description: "Offers safe alternatives where appropriate." },
  ],
  "Code Answer": [
    { id: "technical", name: "Technical Soundness", weight: 40, description: "Provides correct code or reasoning for the requested stack." },
    { id: "integration", name: "Integration Fit", weight: 25, description: "Matches existing patterns, APIs, and constraints." },
    { id: "testing", name: "Testing", weight: 20, description: "Includes meaningful verification or test guidance." },
    { id: "readability", name: "Readability", weight: 15, description: "Keeps the answer maintainable and easy to follow." },
  ],
};

function tokenize(text: string) {
  return new Set(
    text
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, " ")
      .split(/\s+/)
      .filter((word) => word.length > 3),
  );
}

function clampScore(score: number) {
  return Math.max(0, Math.min(10, Math.round(score * 10) / 10));
}

function scoreCandidate(
  candidate: Candidate,
  prompt: string,
  reference: string,
  criteria: Criterion[],
): CandidateScore {
  const responseTokens = tokenize(candidate.response);
  const referenceTokens = tokenize(reference);
  const promptTokens = tokenize(prompt);
  const response = candidate.response.toLowerCase();
  const overlap =
    referenceTokens.size === 0
      ? 0
      : [...referenceTokens].filter((word) => responseTokens.has(word)).length / referenceTokens.size;
  const promptOverlap =
    promptTokens.size === 0
      ? 0
      : [...promptTokens].filter((word) => responseTokens.has(word)).length / promptTokens.size;
  const hasRiskLanguage = /(privacy|risk|review|human|guardrail|rollback|measure|evaluation|audit|safe)/i.test(
    candidate.response,
  );
  const overclaims = /(always|guarantee|fully automate|no need|remove the need|immediately|perfect)/i.test(
    candidate.response,
  );
  const vague = candidate.response.length < 180 || /(just|simply|obvious|later)/i.test(candidate.response);

  const criteriaScores = criteria.map((criterion) => {
    const id = criterion.id.toLowerCase();
    let score = 5.5 + overlap * 3 + promptOverlap * 1.2;
    let note = "Reasonable alignment with the reference and prompt.";

    if (id.includes("safety") || id.includes("risk") || id.includes("policy") || id.includes("boundary")) {
      score = hasRiskLanguage ? score + 1.2 : score - 2;
      if (overclaims) score -= 2;
      note = hasRiskLanguage
        ? "Mentions oversight, measurement, privacy, or rollout risk."
        : "Needs clearer risk controls, oversight, or policy boundaries.";
    }

    if (id.includes("complete") || id.includes("coverage") || id.includes("integration")) {
      score += candidate.response.length > 320 ? 0.8 : -0.8;
      note =
        candidate.response.length > 320
          ? "Covers several concrete parts of the task."
          : "Leaves notable steps or constraints underdeveloped.";
    }

    if (id.includes("clarity") || id.includes("tone") || id.includes("readability")) {
      score += vague ? -0.9 : 0.7;
      note = vague ? "The response reads thin or underspecified." : "The response is concise and easy to scan.";
    }

    if (id.includes("correct") || id.includes("accuracy") || id.includes("technical")) {
      if (overclaims) score -= 2.4;
      note = overclaims
        ? "Contains broad or unsupported claims that weaken correctness."
        : "Avoids obvious unsupported claims and stays near the task.";
    }

    return {
      criterionId: criterion.id,
      score: clampScore(score),
      note,
    };
  });

  const weightTotal = criteria.reduce((sum, criterion) => sum + criterion.weight, 0) || 1;
  const total = clampScore(
    criteriaScores.reduce((sum, item) => {
      const criterion = criteria.find((entry) => entry.id === item.criterionId);
      return sum + item.score * ((criterion?.weight ?? 0) / weightTotal);
    }, 0),
  );

  return {
    candidateId: candidate.id,
    total,
    verdict: total >= 8 ? "pass" : total >= 6 ? "review" : "fail",
    criteria: criteriaScores,
    strengths: [
      overlap > 0.35 ? "Strong reference overlap" : "Some reference alignment",
      hasRiskLanguage ? "Acknowledges operational risk" : "Direct answer structure",
    ],
    risks: [
      overclaims ? "Contains automation or certainty overclaims" : "May need more explicit evidence",
      vague ? "Thin implementation detail" : "Needs final human calibration",
    ],
  };
}

function makeId(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 8)}`;
}

export default function JudgeWorkbench() {
  const [prompt, setPrompt] = useState(initialPrompt);
  const [reference, setReference] = useState(initialReference);
  const [criteria, setCriteria] = useState(initialCriteria);
  const [candidates, setCandidates] = useState(initialCandidates);
  const [selectedCandidateId, setSelectedCandidateId] = useState(initialCandidates[0].id);
  const [judgeMode, setJudgeMode] = useState<"balanced" | "strict" | "lenient">("balanced");

  const scores = useMemo(
    () => candidates.map((candidate) => scoreCandidate(candidate, prompt, reference, criteria)),
    [candidates, criteria, prompt, reference],
  );

  const selectedScore = scores.find((score) => score.candidateId === selectedCandidateId) ?? scores[0];
  const selectedCandidate = candidates.find((candidate) => candidate.id === selectedScore?.candidateId);
  const weightTotal = criteria.reduce((sum, criterion) => sum + criterion.weight, 0);
  const winner = [...scores].sort((a, b) => b.total - a.total)[0];

  useAgentContext({
    description: "Current LLM judge workspace state, including prompt, reference answer, rubric, candidate responses, judge mode, and heuristic scores.",
    value: {
      prompt,
      reference,
      judgeMode,
      criteria,
      candidates,
      scores,
      selectedCandidateId,
    },
  });

  useConfigureSuggestions(
    {
      suggestions: [
        { title: "Tighten rubric", message: "Make this rubric stricter and explain what changed." },
        { title: "Judge Candidate A", message: "Score Candidate A against the rubric and highlight evidence gaps." },
        { title: "Compare outputs", message: "Compare both candidates and recommend the stronger answer." },
      ],
    },
    [prompt, reference, criteria, candidates],
  );

  useFrontendTool(
    {
      name: "loadJudgeExample",
      description: "Load a realistic LLM judge example into the workbench.",
      parameters: z.object({}),
      handler: async () => {
        setPrompt(initialPrompt);
        setReference(initialReference);
        setCriteria(initialCriteria);
        setCandidates(initialCandidates);
        setSelectedCandidateId(initialCandidates[0].id);
        return "Loaded the support triage evaluation example.";
      },
    },
    [],
  );

  useFrontendTool(
    {
      name: "applyRubricTemplate",
      description: "Replace the current rubric with one of the available templates.",
      parameters: z.object({
        templateName: z.enum(["Product QA", "Safety Review", "Code Answer"]).describe("Rubric template to apply"),
      }),
      handler: async ({ templateName }) => {
        const nextCriteria = rubricTemplates[templateName];
        setCriteria(nextCriteria);
        return `Applied ${templateName} rubric with ${nextCriteria.length} criteria.`;
      },
      render: ({ args, status, result }) => (
        <div className="tool-result">
          <ClipboardCheck size={16} />
          <span>{status === ToolCallStatus.Complete ? result : `Applying ${args.templateName ?? "rubric"}...`}</span>
        </div>
      ),
    },
    [],
  );

  useFrontendTool(
    {
      name: "scoreCandidate",
      description: "Score one candidate response in the LLM judge workbench using the current rubric.",
      parameters: z.object({
        candidateLabel: z.string().describe("Candidate label, such as Candidate A or Candidate B"),
      }),
      handler: async ({ candidateLabel }) => {
        const candidate = candidates.find(
          (entry) => entry.label.toLowerCase() === candidateLabel.toLowerCase(),
        );
        if (!candidate) return `No candidate found with label ${candidateLabel}.`;
        const score = scoreCandidate(candidate, prompt, reference, criteria);
        setSelectedCandidateId(candidate.id);
        return `${candidate.label}: ${score.total}/10, verdict ${score.verdict}. Key risk: ${score.risks[0]}.`;
      },
      render: ({ args, status, result }) => (
        <div className="tool-result">
          <Gauge size={16} />
          <span>{status === ToolCallStatus.Complete ? result : `Scoring ${args.candidateLabel ?? "candidate"}...`}</span>
        </div>
      ),
    },
    [candidates, criteria, prompt, reference],
  );

  useFrontendTool(
    {
      name: "flagEvidenceGaps",
      description: "Return a concise list of evidence gaps for the currently selected candidate.",
      parameters: z.object({}),
      handler: async () => {
        if (!selectedScore || !selectedCandidate) return "No selected candidate to review.";
        const lowCriteria = selectedScore.criteria
          .filter((item) => item.score < 7)
          .map((item) => criteria.find((criterion) => criterion.id === item.criterionId)?.name ?? item.criterionId);
        return `${selectedCandidate.label} needs more evidence for: ${lowCriteria.join(", ") || "final calibration only"}.`;
      },
    },
    [criteria, selectedCandidate, selectedScore],
  );

  function updateCriterion(id: string, patch: Partial<Criterion>) {
    setCriteria((current) => current.map((criterion) => (criterion.id === id ? { ...criterion, ...patch } : criterion)));
  }

  function updateCandidate(id: string, patch: Partial<Candidate>) {
    setCandidates((current) => current.map((candidate) => (candidate.id === id ? { ...candidate, ...patch } : candidate)));
  }

  function addCandidate() {
    const next: Candidate = {
      id: makeId("candidate"),
      label: `Candidate ${String.fromCharCode(65 + candidates.length)}`,
      response: "",
    };
    setCandidates((current) => [...current, next]);
    setSelectedCandidateId(next.id);
  }

  function removeCandidate(id: string) {
    setCandidates((current) => current.filter((candidate) => candidate.id !== id));
    if (selectedCandidateId === id) {
      setSelectedCandidateId(candidates.find((candidate) => candidate.id !== id)?.id ?? "");
    }
  }

  return (
    <main className="judge-shell">
      <section className="topbar" aria-label="Workspace summary">
        <div>
          <div className="eyebrow">
            <Bot size={15} />
            CopilotKit judge workspace
          </div>
          <h1>LLM Judge</h1>
        </div>
        <div className="summary-grid">
          <div className="summary-item">
            <span>Winner</span>
            <strong>{winner ? candidates.find((candidate) => candidate.id === winner.candidateId)?.label : "None"}</strong>
          </div>
          <div className="summary-item">
            <span>Top Score</span>
            <strong>{winner?.total.toFixed(1) ?? "0.0"}</strong>
          </div>
          <div className="summary-item">
            <span>Rubric</span>
            <strong>{weightTotal}%</strong>
          </div>
        </div>
      </section>

      <section className="judge-grid" aria-label="LLM judge workbench">
        <div className="left-pane">
          <section className="panel">
            <div className="panel-header">
              <div>
                <span className="section-kicker">Inputs</span>
                <h2>Evaluation Task</h2>
              </div>
              <div className="mode-control" aria-label="Judge mode">
                {(["balanced", "strict", "lenient"] as const).map((mode) => (
                  <button
                    key={mode}
                    className={judgeMode === mode ? "active" : ""}
                    type="button"
                    onClick={() => setJudgeMode(mode)}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </div>
            <label className="field">
              <span>Prompt</span>
              <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={5} />
            </label>
            <label className="field">
              <span>Reference Answer</span>
              <textarea value={reference} onChange={(event) => setReference(event.target.value)} rows={5} />
            </label>
          </section>

          <section className="panel">
            <div className="panel-header">
              <div>
                <span className="section-kicker">Rubric</span>
                <h2>Criteria</h2>
              </div>
              <SlidersHorizontal size={19} />
            </div>
            <div className="criteria-list">
              {criteria.map((criterion) => (
                <article className="criterion-card" key={criterion.id}>
                  <div className="criterion-top">
                    <input
                      aria-label={`${criterion.name} name`}
                      value={criterion.name}
                      onChange={(event) => updateCriterion(criterion.id, { name: event.target.value })}
                    />
                    <label className="weight-field">
                      <span>{criterion.weight}%</span>
                      <input
                        aria-label={`${criterion.name} weight`}
                        max={60}
                        min={5}
                        type="range"
                        value={criterion.weight}
                        onChange={(event) =>
                          updateCriterion(criterion.id, { weight: Number(event.target.value) })
                        }
                      />
                    </label>
                  </div>
                  <textarea
                    aria-label={`${criterion.name} description`}
                    value={criterion.description}
                    onChange={(event) => updateCriterion(criterion.id, { description: event.target.value })}
                    rows={2}
                  />
                </article>
              ))}
            </div>
          </section>
        </div>

        <div className="middle-pane">
          <section className="panel">
            <div className="panel-header">
              <div>
                <span className="section-kicker">Responses</span>
                <h2>Candidates</h2>
              </div>
              <button className="icon-button" type="button" onClick={addCandidate} aria-label="Add candidate">
                <Plus size={18} />
              </button>
            </div>
            <div className="candidate-list">
              {candidates.map((candidate) => {
                const score = scores.find((item) => item.candidateId === candidate.id);
                return (
                  <article
                    className={`candidate-card ${selectedCandidateId === candidate.id ? "selected" : ""}`}
                    key={candidate.id}
                  >
                    <div className="candidate-top">
                      <button type="button" onClick={() => setSelectedCandidateId(candidate.id)}>
                        <span>{candidate.label}</span>
                        <strong>{score?.total.toFixed(1) ?? "0.0"}</strong>
                      </button>
                      <button
                        className="icon-button subtle"
                        type="button"
                        onClick={() => removeCandidate(candidate.id)}
                        aria-label={`Remove ${candidate.label}`}
                        disabled={candidates.length < 2}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                    <label className="field compact">
                      <span>Label</span>
                      <input
                        value={candidate.label}
                        onChange={(event) => updateCandidate(candidate.id, { label: event.target.value })}
                      />
                    </label>
                    <label className="field compact">
                      <span>Response</span>
                      <textarea
                        value={candidate.response}
                        onChange={(event) => updateCandidate(candidate.id, { response: event.target.value })}
                        rows={7}
                      />
                    </label>
                  </article>
                );
              })}
            </div>
          </section>
        </div>

        <aside className="right-pane" aria-label="Judgement result">
          <section className="panel result-panel">
            <div className="panel-header">
              <div>
                <span className="section-kicker">Judgement</span>
                <h2>{selectedCandidate?.label ?? "No Candidate"}</h2>
              </div>
              <Scale size={20} />
            </div>

            {selectedScore ? (
              <>
                <div className={`score-dial ${selectedScore.verdict}`}>
                  <span>{selectedScore.verdict}</span>
                  <strong>{selectedScore.total.toFixed(1)}</strong>
                  <small>out of 10</small>
                </div>

                <div className="score-list">
                  {selectedScore.criteria.map((item) => {
                    const criterion = criteria.find((entry) => entry.id === item.criterionId);
                    return (
                      <div className="score-row" key={item.criterionId}>
                        <div>
                          <strong>{criterion?.name ?? item.criterionId}</strong>
                          <span>{item.note}</span>
                        </div>
                        <meter min={0} max={10} value={item.score} />
                        <b>{item.score.toFixed(1)}</b>
                      </div>
                    );
                  })}
                </div>

                <div className="evidence-grid">
                  <div>
                    <h3>
                      <CheckCircle2 size={16} />
                      Strengths
                    </h3>
                    {selectedScore.strengths.map((item) => (
                      <p key={item}>{item}</p>
                    ))}
                  </div>
                  <div>
                    <h3>
                      <AlertTriangle size={16} />
                      Risks
                    </h3>
                    {selectedScore.risks.map((item) => (
                      <p key={item}>{item}</p>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <div className="empty-state">
                <FileText size={24} />
                <span>No candidate selected</span>
              </div>
            )}
          </section>

          <section className="panel compact-panel">
            <div className="metric-row">
              <BarChart3 size={18} />
              <span>{scores.length} candidates</span>
            </div>
            <div className="metric-row">
              <Sparkles size={18} />
              <span>Copilot tools registered</span>
            </div>
          </section>
        </aside>
      </section>

      <CopilotSidebar
        defaultOpen={false}
        width={430}
        labels={{
          modalHeaderTitle: "Judge Copilot",
          chatInputPlaceholder: "Ask for rubric edits, scoring, or comparisons...",
        }}
      />
    </main>
  );
}
