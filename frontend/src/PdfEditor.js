import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import { Canvas, IText, Rect } from "fabric";
import {
  Upload, Type, Square, ChevronLeft, ChevronRight,
  Download, Save, Undo2, Trash2, Bold, Italic,
  ArrowLeft, FileText, Palette, MousePointer
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const FONT_SIZES = [8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40, 48];
const COLORS = ["#000000", "#333333", "#666666", "#ffffff", "#ff0000", "#0066cc", "#008800", "#ff6600", "#9900cc"];

export default function PdfEditor({ onBack }) {
  const [jobId, setJobId] = useState(null);
  const [pageCount, setPageCount] = useState(0);
  const [pageDims, setPageDims] = useState([]);
  const [currentPage, setCurrentPage] = useState(0);
  const [activeTool, setActiveTool] = useState("select");
  const [fontSize, setFontSize] = useState(14);
  const [fontColor, setFontColor] = useState("#000000");
  const [isBold, setIsBold] = useState(false);
  const [isItalic, setIsItalic] = useState(false);
  const [whiteoutColor, setWhiteoutColor] = useState("#ffffff");
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [filename, setFilename] = useState("");
  const [error, setError] = useState(null);
  const [showColorPicker, setShowColorPicker] = useState(false);
  const [showWhiteoutColorPicker, setShowWhiteoutColorPicker] = useState(false);
  const [canvasScale, setCanvasScale] = useState(1);

  const canvasRef = useRef(null);
  const fabricRef = useRef(null);
  const containerRef = useRef(null);
  const fileInputRef = useRef(null);
  const pageEditsRef = useRef({});
  const textBlocksRef = useRef({});
  const modifiedBlocksRef = useRef({});
  const isDrawingRef = useRef(false);
  const drawStartRef = useRef(null);
  const tempRectRef = useRef(null);
  const activeToolRef = useRef(activeTool);
  const fontSettingsRef = useRef({ fontSize, fontColor, isBold, isItalic });
  const whiteoutColorRef = useRef(whiteoutColor);
  const scaleRef = useRef(1);

  useEffect(() => { activeToolRef.current = activeTool; }, [activeTool]);
  useEffect(() => { fontSettingsRef.current = { fontSize, fontColor, isBold, isItalic }; }, [fontSize, fontColor, isBold, isItalic]);
  useEffect(() => { whiteoutColorRef.current = whiteoutColor; }, [whiteoutColor]);

  // Initialize fabric canvas
  const initCanvas = useCallback(() => {
    if (fabricRef.current) {
      fabricRef.current.dispose();
    }
    const canvas = new Canvas(canvasRef.current, {
      selection: true,
      preserveObjectStacking: true,
    });

    // Mouse down handler for drawing and text
    canvas.on("mouse:down", (opt) => {
      const tool = activeToolRef.current;

      if (tool === "whiteout") {
        isDrawingRef.current = true;
        const pointer = canvas.getViewportPoint(opt.e);
        drawStartRef.current = { x: pointer.x, y: pointer.y };

        const rect = new Rect({
          left: pointer.x,
          top: pointer.y,
          width: 0,
          height: 0,
          fill: whiteoutColorRef.current,
          opacity: 1,
          selectable: true,
          strokeWidth: 0,
        });
        rect.editType = "whiteout";
        rect.editWhiteoutColor = whiteoutColorRef.current;
        tempRectRef.current = rect;
        canvas.add(rect);
        canvas.selection = false;
      } else if (tool === "text" && !opt.target) {
        const pointer = canvas.getViewportPoint(opt.e);
        const settings = fontSettingsRef.current;
        const textbox = new IText("Tekst", {
          left: pointer.x,
          top: pointer.y,
          fontSize: settings.fontSize,
          fill: settings.fontColor,
          fontWeight: settings.isBold ? "bold" : "normal",
          fontStyle: settings.isItalic ? "italic" : "normal",
          fontFamily: "Helvetica",
          editable: true,
          selectable: true,
        });
        textbox.editType = "text";
        textbox.editFontSize = settings.fontSize;
        textbox.editFontColor = settings.fontColor;
        textbox.editBold = settings.isBold;
        textbox.editItalic = settings.isItalic;
        canvas.add(textbox);
        canvas.setActiveObject(textbox);
        textbox.enterEditing();
        textbox.selectAll();
        canvas.renderAll();
      }
    });

    canvas.on("mouse:move", (opt) => {
      if (!isDrawingRef.current || !tempRectRef.current) return;
      const pointer = canvas.getViewportPoint(opt.e);
      const start = drawStartRef.current;
      const left = Math.min(start.x, pointer.x);
      const top = Math.min(start.y, pointer.y);
      const width = Math.abs(pointer.x - start.x);
      const height = Math.abs(pointer.y - start.y);
      tempRectRef.current.set({ left, top, width, height });
      canvas.renderAll();
    });

    canvas.on("mouse:up", () => {
      if (!isDrawingRef.current) return;
      isDrawingRef.current = false;
      if (tempRectRef.current && tempRectRef.current.width < 3 && tempRectRef.current.height < 3) {
        canvas.remove(tempRectRef.current);
      }
      tempRectRef.current = null;
      canvas.selection = true;
    });

    fabricRef.current = canvas;
    return canvas;
  }, []);

  // Fetch text blocks for current page and create clickable areas
  const loadTextBlocks = useCallback(async (pageNum, scale) => {
    if (!jobId || !fabricRef.current) return;

    try {
      const res = await axios.get(`${API}/editor/text-blocks/${jobId}/${pageNum}`);
      const blocks = res.data.blocks;
      textBlocksRef.current[pageNum] = blocks;

      const canvas = fabricRef.current;

      // Create invisible clickable regions for each text block
      blocks.forEach((block, idx) => {
        const rect = new Rect({
          left: block.x * scale,
          top: block.y * scale,
          width: block.width * scale,
          height: block.height * scale,
          fill: "transparent",
          stroke: "transparent",
          strokeWidth: 0,
          selectable: false,
          evented: true,
          hoverCursor: "text",
          opacity: 0,
        });
        rect.textBlockIdx = idx;
        rect.textBlockData = block;
        rect.editType = "textBlockHitArea";

        // On double-click, enter edit mode for this text block
        rect.on("mousedblclick", () => {
          activateTextBlockEditing(block, idx, scale, canvas);
        });

        canvas.add(rect);
      });
      canvas.renderAll();
    } catch (err) {
      console.error("Failed to load text blocks:", err);
    }
  }, [jobId]);

  // Activate editing for a specific text block
  const activateTextBlockEditing = (block, idx, scale, canvas) => {
    // Remove the hit area rect for this block
    const hitAreas = canvas.getObjects().filter(
      obj => obj.editType === "textBlockHitArea" && obj.textBlockIdx === idx
    );
    hitAreas.forEach(h => canvas.remove(h));

    // Create editable IText at the block's position
    const textObj = new IText(block.text, {
      left: block.x * scale,
      top: block.y * scale,
      fontSize: block.fontSize * scale,
      fill: block.fontColor,
      fontWeight: block.bold ? "bold" : "normal",
      fontStyle: block.italic ? "italic" : "normal",
      fontFamily: "Helvetica",
      editable: true,
      selectable: true,
      backgroundColor: "rgba(200, 220, 255, 0.3)",
    });
    textObj.editType = "replaceText";
    textObj.originalBlock = block;
    textObj.blockIdx = idx;
    textObj.editFontSize = block.fontSize;
    textObj.editFontColor = block.fontColor;
    textObj.editBold = block.bold;
    textObj.editItalic = block.italic;

    canvas.add(textObj);
    canvas.setActiveObject(textObj);
    textObj.enterEditing();
    textObj.selectAll();
    canvas.renderAll();
  };

  // Load page
  const loadPage = useCallback(async (pageNum) => {
    if (!jobId || !fabricRef.current) return;
    const canvas = fabricRef.current;

    const imgUrl = `${API}/editor/page/${jobId}/${pageNum}?t=${Date.now()}`;
    const imgEl = document.getElementById("editor-bg-image");
    if (!imgEl) return;

    await new Promise((resolve) => {
      imgEl.onload = resolve;
      imgEl.src = imgUrl;
    });

    const container = containerRef.current;
    if (!container) return;

    const maxWidth = Math.min(container.clientWidth - 48, 900);
    const pageDim = pageDims[pageNum];
    // The image is rendered at 2x, so natural dimensions are PDF*2
    const imgNaturalW = imgEl.naturalWidth;
    const scale = maxWidth / imgNaturalW;
    const canvasWidth = Math.round(imgNaturalW * scale);
    const canvasHeight = Math.round(imgEl.naturalHeight * scale);

    // The PDF->canvas scale = canvasWidth / pdfWidth = (imgNaturalW * scale) / pdfWidth
    // Since imgNaturalW = pdfWidth * 2 (rendered at 2x), pdfToCanvas = 2 * scale
    const pdfToCanvas = (imgNaturalW / pageDim.width) * scale;
    scaleRef.current = pdfToCanvas;
    setCanvasScale(pdfToCanvas);

    imgEl.style.width = canvasWidth + "px";
    imgEl.style.height = canvasHeight + "px";

    canvas.setDimensions({ width: canvasWidth, height: canvasHeight });
    canvas.clear();
    canvas.renderAll();

    // Restore user edits for this page
    restorePageState(pageNum);

    // Load text blocks for click-to-edit
    await loadTextBlocks(pageNum, pdfToCanvas);
  }, [jobId, pageDims, loadTextBlocks]);

  // Save current canvas objects for a page (only user edits, not hit areas)
  const savePageState = useCallback((pageNum) => {
    if (!fabricRef.current) return;
    const canvas = fabricRef.current;
    const objects = canvas.getObjects()
      .filter(obj => obj.editType && obj.editType !== "textBlockHitArea")
      .map(obj => {
        const json = obj.toJSON();
        json.editType = obj.editType;
        json.editFontSize = obj.editFontSize;
        json.editFontColor = obj.editFontColor;
        json.editBold = obj.editBold;
        json.editItalic = obj.editItalic;
        json.editWhiteoutColor = obj.editWhiteoutColor;
        if (obj.originalBlock) {
          json.originalBlock = obj.originalBlock;
        }
        return json;
      });
    pageEditsRef.current[pageNum] = objects;
  }, []);

  // Restore saved objects for a page
  const restorePageState = useCallback((pageNum) => {
    if (!fabricRef.current) return;
    const objects = pageEditsRef.current[pageNum];
    if (!objects || objects.length === 0) return;

    const canvas = fabricRef.current;
    objects.forEach(objData => {
      let obj;
      if (objData.editType === "whiteout") {
        obj = new Rect({
          left: objData.left,
          top: objData.top,
          width: objData.width,
          height: objData.height,
          fill: objData.fill,
          opacity: 1,
          scaleX: objData.scaleX || 1,
          scaleY: objData.scaleY || 1,
          selectable: true,
          strokeWidth: 0,
        });
        obj.editType = "whiteout";
        obj.editWhiteoutColor = objData.editWhiteoutColor || objData.fill;
      } else if (objData.editType === "text" || objData.editType === "replaceText") {
        obj = new IText(objData.text || "Tekst", {
          left: objData.left,
          top: objData.top,
          fontSize: objData.fontSize,
          fill: objData.fill,
          fontWeight: objData.fontWeight || "normal",
          fontStyle: objData.fontStyle || "normal",
          fontFamily: objData.fontFamily || "Helvetica",
          scaleX: objData.scaleX || 1,
          scaleY: objData.scaleY || 1,
          editable: true,
          selectable: true,
        });
        obj.editType = objData.editType;
        obj.editFontSize = objData.editFontSize;
        obj.editFontColor = objData.editFontColor;
        obj.editBold = objData.editBold;
        obj.editItalic = objData.editItalic;
        if (objData.originalBlock) {
          obj.originalBlock = objData.originalBlock;
        }
      }
      if (obj) canvas.add(obj);
    });
    canvas.renderAll();
  }, []);

  // Update cursor based on active tool
  useEffect(() => {
    if (!fabricRef.current) return;
    const canvas = fabricRef.current;
    if (activeTool === "text") {
      canvas.defaultCursor = "text";
      canvas.hoverCursor = "text";
    } else if (activeTool === "whiteout") {
      canvas.defaultCursor = "crosshair";
      canvas.hoverCursor = "crosshair";
    } else {
      canvas.defaultCursor = "default";
      canvas.hoverCursor = "default";
    }
  }, [activeTool]);

  // Handle file upload
  const handleUpload = async (selectedFile) => {
    if (!selectedFile) return;
    const ext = selectedFile.name.split(".").pop().toLowerCase();
    if (ext !== "pdf") {
      setError("Samo PDF datoteke su podrzane");
      return;
    }
    setError(null);
    setUploading(true);
    setSaved(false);

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const res = await axios.post(`${API}/editor/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setJobId(res.data.job_id);
      setPageCount(res.data.page_count);
      setPageDims(res.data.page_dims);
      setFilename(res.data.filename);
      setCurrentPage(0);
      pageEditsRef.current = {};
      textBlocksRef.current = {};
      modifiedBlocksRef.current = {};
    } catch (e) {
      setError(e.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  // Init canvas once we have jobId
  useEffect(() => {
    if (jobId && canvasRef.current && !fabricRef.current) {
      initCanvas();
    }
  }, [jobId, initCanvas]);

  // Load page when canvas is ready or page changes
  useEffect(() => {
    if (jobId && fabricRef.current && pageDims.length > 0) {
      loadPage(currentPage);
    }
  }, [currentPage, jobId, loadPage, pageDims]);

  // Switch pages
  const goToPage = (pageNum) => {
    if (pageNum < 0 || pageNum >= pageCount) return;
    savePageState(currentPage);
    setCurrentPage(pageNum);
  };

  // Delete selected object
  const deleteSelected = () => {
    if (!fabricRef.current) return;
    const canvas = fabricRef.current;
    const active = canvas.getActiveObject();
    if (active && active.editType && active.editType !== "textBlockHitArea") {
      canvas.remove(active);
      canvas.renderAll();
    }
  };

  // Undo last added object
  const undoLast = () => {
    if (!fabricRef.current) return;
    const canvas = fabricRef.current;
    const objects = canvas.getObjects().filter(
      obj => obj.editType && obj.editType !== "textBlockHitArea"
    );
    if (objects.length > 0) {
      canvas.remove(objects[objects.length - 1]);
      canvas.renderAll();
    }
  };

  // Save edits to backend
  const handleSave = async () => {
    if (!fabricRef.current || !jobId) return;
    savePageState(currentPage);
    setSaving(true);
    setError(null);
    setSaved(false);

    try {
      const allEdits = [];

      for (let p = 0; p < pageCount; p++) {
        const objects = pageEditsRef.current[p];
        if (!objects || objects.length === 0) continue;

        const pageDim = pageDims[p];
        const pdfToCanvas = scaleRef.current;
        const canvasToPdf = 1 / pdfToCanvas;

        objects.forEach(obj => {
          if (obj.editType === "whiteout") {
            allEdits.push({
              type: "whiteout",
              page: p,
              x: (obj.left || 0) * canvasToPdf,
              y: (obj.top || 0) * canvasToPdf,
              width: (obj.width || 0) * (obj.scaleX || 1) * canvasToPdf,
              height: (obj.height || 0) * (obj.scaleY || 1) * canvasToPdf,
              backgroundColor: obj.editWhiteoutColor || obj.fill || "#ffffff",
            });
          } else if (obj.editType === "text") {
            allEdits.push({
              type: "text",
              page: p,
              x: (obj.left || 0) * canvasToPdf,
              y: (obj.top || 0) * canvasToPdf,
              width: (obj.width || 0) * (obj.scaleX || 1) * canvasToPdf,
              height: (obj.height || 0) * (obj.scaleY || 1) * canvasToPdf,
              text: obj.text || "",
              fontSize: (obj.editFontSize || obj.fontSize || 14) * (obj.scaleX || 1),
              fontColor: obj.editFontColor || obj.fill || "#000000",
              bold: obj.editBold || obj.fontWeight === "bold",
              italic: obj.editItalic || obj.fontStyle === "italic",
            });
          } else if (obj.editType === "replaceText" && obj.originalBlock) {
            const block = obj.originalBlock;
            allEdits.push({
              type: "replace",
              page: p,
              x: block.x,
              y: block.y,
              width: block.width,
              height: block.height,
              text: obj.text || "",
              fontSize: block.fontSize,
              fontColor: block.fontColor,
              bold: block.bold,
              italic: block.italic,
              origX: block.x,
              origY: block.y,
              origWidth: block.width,
              origHeight: block.height,
            });
          }
        });
      }

      await axios.post(`${API}/editor/save/${jobId}`, { edits: allEdits });
      setSaved(true);
    } catch (e) {
      setError(e.response?.data?.detail || "Greska pri spremanju");
    } finally {
      setSaving(false);
    }
  };

  // Download edited PDF
  const handleDownload = async () => {
    if (!saved) {
      await handleSave();
    }
    try {
      const res = await axios.get(`${API}/editor/download/${jobId}`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", filename.replace(".pdf", "_edited.pdf"));
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      setError("Download failed");
    }
  };

  // Keyboard shortcuts
  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === "Delete" || e.key === "Backspace") {
        if (fabricRef.current) {
          const active = fabricRef.current.getActiveObject();
          if (active && !active.isEditing) {
            deleteSelected();
          }
        }
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "z") {
        if (fabricRef.current) {
          const active = fabricRef.current.getActiveObject();
          if (!active || !active.isEditing) {
            e.preventDefault();
            undoLast();
          }
        }
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  // Cleanup canvas on unmount
  useEffect(() => {
    return () => {
      if (fabricRef.current) {
        fabricRef.current.dispose();
        fabricRef.current = null;
      }
    };
  }, []);

  // No file uploaded - show upload screen
  if (!jobId) {
    return (
      <div className="editor-wrapper" data-testid="pdf-editor">
        <div className="editor-header">
          <button className="editor-back-btn" onClick={onBack} data-testid="editor-back-btn">
            <ArrowLeft size={18} /> Natrag
          </button>
          <h1 className="editor-title">
            <FileText size={20} /> PDF Editor
          </h1>
        </div>
        <div className="editor-upload-area" data-testid="editor-upload-section">
          <div
            className={`editor-dropzone ${uploading ? "uploading" : ""}`}
            onClick={() => fileInputRef.current?.click()}
            data-testid="editor-upload-dropzone"
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              className="hidden"
              data-testid="editor-file-input"
              onChange={(e) => handleUpload(e.target.files[0])}
            />
            {uploading ? (
              <div className="upload-loading">
                <div className="spinner" />
                <span>Ucitavanje PDF-a...</span>
              </div>
            ) : (
              <>
                <Upload size={36} strokeWidth={1.5} />
                <p className="editor-drop-text">
                  Povucite PDF ovdje ili <span className="upload-link">odaberite datoteku</span>
                </p>
                <span className="format-pill">.pdf</span>
                <p className="editor-hint">Dvaput kliknite na tekst za uredivanje</p>
              </>
            )}
          </div>
          {error && <div className="editor-error" data-testid="editor-error">{error}</div>}
        </div>
      </div>
    );
  }

  return (
    <div className="editor-wrapper" data-testid="pdf-editor">
      {/* Header */}
      <div className="editor-header">
        <button className="editor-back-btn" onClick={onBack} data-testid="editor-back-btn">
          <ArrowLeft size={18} /> Natrag
        </button>
        <span className="editor-filename" data-testid="editor-filename">{filename}</span>
        <div className="editor-header-actions">
          <button
            className="editor-save-btn"
            onClick={handleSave}
            disabled={saving}
            data-testid="editor-save-btn"
          >
            <Save size={16} /> {saving ? "Spremam..." : "Spremi"}
          </button>
          <button
            className="editor-download-btn"
            onClick={handleDownload}
            data-testid="editor-download-btn"
          >
            <Download size={16} /> Preuzmi PDF
          </button>
        </div>
      </div>

      {error && <div className="editor-error" data-testid="editor-error">{error}</div>}
      {saved && !error && <div className="editor-saved" data-testid="editor-saved-msg">Spremljeno uspjesno!</div>}

      <div className="editor-body">
        {/* Toolbar */}
        <div className="editor-toolbar" data-testid="editor-toolbar">
          <div className="toolbar-section">
            <span className="toolbar-label">Alati</span>
            <button
              className={`toolbar-btn ${activeTool === "select" ? "active" : ""}`}
              onClick={() => setActiveTool("select")}
              title="Odaberi / Pomakni (dvaput klikni na tekst za uredivanje)"
              data-testid="tool-select"
            >
              <MousePointer size={16} />
            </button>
            <button
              className={`toolbar-btn ${activeTool === "text" ? "active" : ""}`}
              onClick={() => setActiveTool("text")}
              title="Dodaj novi tekst"
              data-testid="tool-text"
            >
              <Type size={16} />
            </button>
            <button
              className={`toolbar-btn ${activeTool === "whiteout" ? "active" : ""}`}
              onClick={() => setActiveTool("whiteout")}
              title="Whiteout - prekrij sadrzaj"
              data-testid="tool-whiteout"
            >
              <Square size={16} />
            </button>
          </div>

          {/* Text options */}
          {activeTool === "text" && (
            <div className="toolbar-section">
              <span className="toolbar-label">Tekst</span>
              <select
                className="toolbar-select"
                value={fontSize}
                onChange={(e) => setFontSize(Number(e.target.value))}
                data-testid="font-size-select"
              >
                {FONT_SIZES.map(s => <option key={s} value={s}>{s}px</option>)}
              </select>
              <button
                className={`toolbar-btn small ${isBold ? "active" : ""}`}
                onClick={() => setIsBold(!isBold)}
                data-testid="toggle-bold"
              >
                <Bold size={14} />
              </button>
              <button
                className={`toolbar-btn small ${isItalic ? "active" : ""}`}
                onClick={() => setIsItalic(!isItalic)}
                data-testid="toggle-italic"
              >
                <Italic size={14} />
              </button>
              <div className="color-picker-wrap">
                <button
                  className="toolbar-btn color-btn"
                  onClick={() => setShowColorPicker(!showColorPicker)}
                  data-testid="text-color-btn"
                >
                  <Palette size={14} />
                  <span className="color-dot" style={{ backgroundColor: fontColor }}></span>
                </button>
                {showColorPicker && (
                  <div className="color-popup" data-testid="color-picker-popup">
                    {COLORS.map(c => (
                      <button
                        key={c}
                        className={`color-swatch ${fontColor === c ? "active" : ""}`}
                        style={{ backgroundColor: c }}
                        onClick={() => { setFontColor(c); setShowColorPicker(false); }}
                        data-testid={`color-swatch-${c.replace('#','')}`}
                      />
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Whiteout options */}
          {activeTool === "whiteout" && (
            <div className="toolbar-section">
              <span className="toolbar-label">Boja prekrivanja</span>
              <div className="color-picker-wrap">
                <button
                  className="toolbar-btn color-btn"
                  onClick={() => setShowWhiteoutColorPicker(!showWhiteoutColorPicker)}
                  data-testid="whiteout-color-btn"
                >
                  <Palette size={14} />
                  <span className="color-dot" style={{ backgroundColor: whiteoutColor }}></span>
                </button>
                {showWhiteoutColorPicker && (
                  <div className="color-popup" data-testid="whiteout-color-picker">
                    {COLORS.map(c => (
                      <button
                        key={c}
                        className={`color-swatch ${whiteoutColor === c ? "active" : ""}`}
                        style={{ backgroundColor: c }}
                        onClick={() => { setWhiteoutColor(c); setShowWhiteoutColorPicker(false); }}
                        data-testid={`whiteout-swatch-${c.replace('#','')}`}
                      />
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="toolbar-section">
            <span className="toolbar-label">Akcije</span>
            <button className="toolbar-btn" onClick={undoLast} title="Vrati (Ctrl+Z)" data-testid="undo-btn">
              <Undo2 size={16} />
            </button>
            <button className="toolbar-btn" onClick={deleteSelected} title="Obrisi odabrano (Del)" data-testid="delete-btn">
              <Trash2 size={16} />
            </button>
          </div>

          <div className="toolbar-hint">
            <span>Dvaput klikni na tekst za uredivanje</span>
          </div>
        </div>

        {/* Canvas area */}
        <div className="editor-canvas-container" ref={containerRef} data-testid="editor-canvas-container">
          <div className="editor-canvas-wrapper">
            <img
              id="editor-bg-image"
              className="editor-bg-image"
              alt="PDF page"
              data-testid="editor-bg-image"
            />
            <canvas ref={canvasRef} data-testid="editor-canvas" />
          </div>
        </div>

        {/* Page navigation */}
        {pageCount > 1 && (
          <div className="editor-page-nav" data-testid="editor-page-nav">
            <button
              className="page-nav-btn"
              disabled={currentPage === 0}
              onClick={() => goToPage(currentPage - 1)}
              data-testid="editor-prev-page"
            >
              <ChevronLeft size={18} />
            </button>
            <span className="page-indicator" data-testid="editor-page-indicator">
              Stranica {currentPage + 1} / {pageCount}
            </span>
            <button
              className="page-nav-btn"
              disabled={currentPage >= pageCount - 1}
              onClick={() => goToPage(currentPage + 1)}
              data-testid="editor-next-page"
            >
              <ChevronRight size={18} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
