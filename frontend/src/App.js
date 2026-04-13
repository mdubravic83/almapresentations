import { useState, useEffect, useRef, useCallback } from "react";
import "@/App.css";
import axios from "axios";
import {
  Upload,
  FileText,
  Languages,
  Download,
  ChevronDown,
  RotateCcw,
  AlertCircle,
  Check,
  ArrowRight,
  Mic,
  GraduationCap,
  Briefcase,
  X,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const LANGUAGES = [
  { value: "English", label: "English" },
  { value: "German", label: "Deutsch (German)" },
  { value: "French", label: "Francais (French)" },
  { value: "Spanish", label: "Espanol (Spanish)" },
  { value: "Italian", label: "Italiano (Italian)" },
  { value: "Portuguese", label: "Portugues (Portuguese)" },
  { value: "Russian", label: "Russian" },
  { value: "Chinese (Simplified)", label: "Chinese (Simplified)" },
  { value: "Japanese", label: "Japanese" },
  { value: "Korean", label: "Korean" },
  { value: "Arabic", label: "Arabic" },
  { value: "Dutch", label: "Nederlands (Dutch)" },
  { value: "Polish", label: "Polski (Polish)" },
  { value: "Turkish", label: "Turkce (Turkish)" },
  { value: "Swedish", label: "Svenska (Swedish)" },
  { value: "Czech", label: "Cestina (Czech)" },
  { value: "Croatian", label: "Hrvatski (Croatian)" },
];

const TONES = [
  { value: "formal", label: "Formal", icon: Briefcase, desc: "Professional, precise" },
  { value: "academic", label: "Academic", icon: GraduationCap, desc: "Scholarly, technical" },
  { value: "general", label: "General", icon: Mic, desc: "Natural, conversational" },
];

function App() {
  const [step, setStep] = useState("upload");
  const [file, setFile] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [jobInfo, setJobInfo] = useState(null);
  const [language, setLanguage] = useState("English");
  const [customLanguage, setCustomLanguage] = useState("");
  const [useCustom, setUseCustom] = useState(false);
  const [tone, setTone] = useState("formal");
  const [progress, setProgress] = useState(0);
  const [translatedCount, setTranslatedCount] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [status, setStatus] = useState("");
  const [preview, setPreview] = useState([]);
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [showLangDropdown, setShowLangDropdown] = useState(false);
  const fileInputRef = useRef(null);
  const pollRef = useRef(null);
  const dropdownRef = useRef(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClick = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setShowLangDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const handleUpload = async (selectedFile) => {
    if (!selectedFile) return;
    if (!selectedFile.name.endsWith(".pptx")) {
      setError("Only .pptx files are supported");
      return;
    }
    setError(null);
    setUploading(true);
    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const res = await axios.post(`${API}/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setFile(selectedFile);
      setJobId(res.data.id);
      setJobInfo(res.data);
      setTotalCount(res.data.total_segments);
      setStep("configure");
    } catch (e) {
      setError(e.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) handleUpload(droppedFile);
  };

  const startTranslation = async () => {
    const targetLang = useCustom ? customLanguage : language;
    if (!targetLang.trim()) {
      setError("Please select or enter a target language");
      return;
    }
    setError(null);
    setStep("translating");
    setProgress(0);
    setTranslatedCount(0);

    try {
      await axios.post(`${API}/translate/${jobId}`, {
        target_language: targetLang,
        tone,
      });
      startPolling();
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to start translation");
      setStep("configure");
    }
  };

  const startPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await axios.get(`${API}/progress/${jobId}`);
        const data = res.data;
        setProgress(Math.round(data.progress));
        setTranslatedCount(data.translated_segments);
        setTotalCount(data.total_segments);
        setStatus(data.status);

        if (data.status === "completed") {
          clearInterval(pollRef.current);
          pollRef.current = null;
          // Load preview
          const previewRes = await axios.get(`${API}/preview/${jobId}`);
          setPreview(previewRes.data.segments);
          setStep("complete");
        } else if (data.status === "error") {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setError(data.error_message || "Translation failed");
          setStep("configure");
        }
      } catch {
        // Ignore polling errors
      }
    }, 1500);
  }, [jobId]);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const handleDownload = async () => {
    try {
      const res = await axios.get(`${API}/download/${jobId}`, {
        responseType: "blob",
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      const originalName = jobInfo?.filename?.replace(".pptx", "") || "presentation";
      const targetLang = useCustom ? customLanguage : language;
      link.setAttribute("download", `${originalName}_${targetLang}.pptx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      setError("Download failed. Please try again.");
    }
  };

  const resetAll = () => {
    setStep("upload");
    setFile(null);
    setJobId(null);
    setJobInfo(null);
    setProgress(0);
    setTranslatedCount(0);
    setPreview([]);
    setError(null);
    setStatus("");
    if (pollRef.current) clearInterval(pollRef.current);
  };

  // Group preview by slide
  const groupedPreview = preview.reduce((acc, seg) => {
    if (!acc[seg.slide_num]) acc[seg.slide_num] = [];
    acc[seg.slide_num].push(seg);
    return acc;
  }, {});

  return (
    <div className="app-wrapper">
      {/* Header */}
      <header className="app-header" data-testid="app-header">
        <div className="header-inner">
          <div className="header-brand">
            <Languages size={22} strokeWidth={2.5} />
            <span className="header-title">SlideTranslate</span>
          </div>
          <span className="header-badge">AI-Powered</span>
        </div>
      </header>

      <main className="app-main">
        {/* Step indicator */}
        <div className="steps-bar" data-testid="steps-bar">
          {["Upload", "Configure", "Translate", "Done"].map((label, i) => {
            const stepMap = ["upload", "configure", "translating", "complete"];
            const currentIdx = stepMap.indexOf(step);
            const isActive = i === currentIdx;
            const isDone = i < currentIdx;
            return (
              <div key={label} className={`step-item ${isActive ? "active" : ""} ${isDone ? "done" : ""}`}>
                <div className="step-circle">
                  {isDone ? <Check size={14} strokeWidth={3} /> : <span>{i + 1}</span>}
                </div>
                <span className="step-label">{label}</span>
                {i < 3 && <ArrowRight size={14} className="step-arrow" />}
              </div>
            );
          })}
        </div>

        {/* Error banner */}
        {error && (
          <div className="error-banner" data-testid="error-banner">
            <AlertCircle size={16} />
            <span>{error}</span>
            <button onClick={() => setError(null)} data-testid="dismiss-error-btn">
              <X size={14} />
            </button>
          </div>
        )}

        {/* STEP: Upload */}
        {step === "upload" && (
          <section className="content-section" data-testid="upload-section">
            <h1 className="section-title">Translate your presentation</h1>
            <p className="section-desc">
              Upload a .pptx file and get it translated to any language using AI
            </p>
            <div
              className={`upload-zone ${dragOver ? "drag-over" : ""} ${uploading ? "uploading" : ""}`}
              data-testid="upload-dropzone"
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pptx"
                className="hidden"
                data-testid="file-input"
                onChange={(e) => handleUpload(e.target.files[0])}
              />
              {uploading ? (
                <div className="upload-loading">
                  <div className="spinner" />
                  <span>Processing file...</span>
                </div>
              ) : (
                <>
                  <div className="upload-icon-wrap">
                    <Upload size={28} strokeWidth={1.5} />
                  </div>
                  <p className="upload-main-text">
                    Drop your .pptx file here or <span className="upload-link">browse</span>
                  </p>
                  <p className="upload-sub-text">PowerPoint files only, max 50MB</p>
                </>
              )}
            </div>
          </section>
        )}

        {/* STEP: Configure */}
        {step === "configure" && (
          <section className="content-section" data-testid="configure-section">
            <div className="file-info-bar" data-testid="file-info-bar">
              <FileText size={18} />
              <span className="file-name">{jobInfo?.filename}</span>
              <span className="file-segments">{jobInfo?.total_segments} text segments</span>
            </div>

            <h2 className="section-title-sm">Translation settings</h2>

            {/* Language */}
            <div className="field-group">
              <label className="field-label">TARGET LANGUAGE</label>
              {!useCustom ? (
                <div className="lang-select-wrap" ref={dropdownRef}>
                  <button
                    className="lang-select-btn"
                    data-testid="language-select"
                    onClick={() => setShowLangDropdown(!showLangDropdown)}
                  >
                    <span>{LANGUAGES.find(l => l.value === language)?.label || language}</span>
                    <ChevronDown size={16} />
                  </button>
                  {showLangDropdown && (
                    <div className="lang-dropdown" data-testid="language-dropdown">
                      {LANGUAGES.map((l) => (
                        <button
                          key={l.value}
                          className={`lang-option ${language === l.value ? "selected" : ""}`}
                          data-testid={`lang-option-${l.value.toLowerCase().replace(/[^a-z]/g, '-')}`}
                          onClick={() => { setLanguage(l.value); setShowLangDropdown(false); }}
                        >
                          {l.label}
                        </button>
                      ))}
                      <div className="lang-divider" />
                      <button
                        className="lang-option other"
                        data-testid="lang-option-other"
                        onClick={() => { setUseCustom(true); setShowLangDropdown(false); }}
                      >
                        Other language...
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                <div className="custom-lang-wrap">
                  <input
                    type="text"
                    className="custom-lang-input"
                    data-testid="custom-language-input"
                    placeholder="Enter language name (e.g. Hindi, Serbian...)"
                    value={customLanguage}
                    onChange={(e) => setCustomLanguage(e.target.value)}
                    autoFocus
                  />
                  <button
                    className="custom-lang-back"
                    data-testid="back-to-list-btn"
                    onClick={() => { setUseCustom(false); setCustomLanguage(""); }}
                  >
                    Back to list
                  </button>
                </div>
              )}
            </div>

            {/* Tone */}
            <div className="field-group">
              <label className="field-label">TRANSLATION TONE</label>
              <div className="tone-group" data-testid="tone-selector">
                {TONES.map((t) => {
                  const Icon = t.icon;
                  return (
                    <button
                      key={t.value}
                      className={`tone-btn ${tone === t.value ? "active" : ""}`}
                      data-testid={`tone-${t.value}`}
                      onClick={() => setTone(t.value)}
                    >
                      <Icon size={18} />
                      <span className="tone-label">{t.label}</span>
                      <span className="tone-desc">{t.desc}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="actions-row">
              <button className="btn-secondary" data-testid="back-to-upload-btn" onClick={resetAll}>
                <RotateCcw size={16} /> Start over
              </button>
              <button className="btn-primary" data-testid="translate-submit-button" onClick={startTranslation}>
                <Languages size={16} /> Translate presentation
              </button>
            </div>
          </section>
        )}

        {/* STEP: Translating */}
        {step === "translating" && (
          <section className="content-section" data-testid="translating-section">
            <h2 className="section-title-sm">Translating...</h2>
            <p className="section-desc">
              Processing {totalCount} text segments with AI
            </p>

            <div className="progress-wrap" data-testid="progress-bar-container">
              <div className="progress-track">
                <div
                  className="progress-fill"
                  style={{ width: `${progress}%` }}
                  data-testid="progress-fill"
                />
              </div>
              <div className="progress-info">
                <span className="progress-pct" data-testid="progress-percentage">
                  {progress}%
                </span>
                <span className="progress-count">
                  {translatedCount} / {totalCount} segments
                </span>
              </div>
            </div>

            <div className="translate-status">
              <div className="spinner small" />
              <span>AI is translating your presentation...</span>
            </div>
          </section>
        )}

        {/* STEP: Complete */}
        {step === "complete" && (
          <section className="content-section wide" data-testid="complete-section">
            <div className="complete-header">
              <div>
                <h2 className="section-title-sm">Translation complete</h2>
                <p className="section-desc">
                  {preview.length} segments translated to {useCustom ? customLanguage : language}
                </p>
              </div>
              <div className="complete-actions">
                <button className="btn-secondary" data-testid="new-translation-btn" onClick={resetAll}>
                  <RotateCcw size={16} /> New translation
                </button>
                <button className="btn-primary" data-testid="download-button" onClick={handleDownload}>
                  <Download size={16} /> Download .pptx
                </button>
              </div>
            </div>

            {/* Preview */}
            <div className="preview-section" data-testid="preview-section">
              <h3 className="preview-title">Preview</h3>
              <div className="preview-list">
                {Object.entries(groupedPreview).map(([slideNum, segs]) => (
                  <div key={slideNum} className="preview-slide" data-testid={`preview-slide-${slideNum}`}>
                    <div className="slide-badge">Slide {slideNum}</div>
                    {segs.map((seg) => (
                      <div key={seg.idx} className="preview-row">
                        <div className="preview-col original">
                          <span className="col-label">Original</span>
                          <p>{seg.original}</p>
                        </div>
                        <div className="preview-col translated">
                          <span className="col-label">Translated</span>
                          <p>{seg.translated}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}
      </main>

      <footer className="app-footer">
        <span>SlideTranslate</span>
        <span className="footer-sep">/</span>
        <span>Powered by OpenAI o4-mini</span>
      </footer>
    </div>
  );
}

export default App;
