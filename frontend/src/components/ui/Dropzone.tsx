import {
  type ChangeEvent,
  type DragEvent,
  type ReactElement,
  type ReactNode,
  useRef,
  useState,
} from "react";

interface DropzoneProps {
  /* Se invoca cuando el usuario suelta o selecciona un archivo. */
  onFile: (file: File) => void;
  /* Mime types o extensiones aceptadas, ej. ".json,application/json". */
  accept?: string;
  /* Texto principal grande. */
  label: ReactNode;
  /* Texto secundario en mono pequeño. */
  sub?: ReactNode;
  /* Si se pasa, se renderiza un botón "explorar…" debajo. */
  showBrowseButton?: boolean;
  disabled?: boolean;
}

/* Drop zone con file picker oculto. CSS global `.dropzone` definido
   en `configuration.css`. Acepta drag-and-drop nativo del browser y
   fallback a `<input type="file">` invisible. */
export function Dropzone({
  onFile,
  accept,
  label,
  sub,
  showBrowseButton = true,
  disabled = false,
}: DropzoneProps): ReactElement {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [hover, setHover] = useState(false);

  const open = () => {
    if (disabled) return;
    inputRef.current?.click();
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setHover(false);
    if (disabled) return;
    const file = e.dataTransfer?.files?.[0];
    if (file) onFile(file);
  };

  const onChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) onFile(file);
    // Reset para que el mismo archivo se pueda volver a seleccionar.
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div
      className={`dropzone${hover ? " is-hover" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setHover(true);
      }}
      onDragLeave={() => setHover(false)}
      onDrop={onDrop}
      // biome-ignore lint/a11y/useSemanticElements: dropzone necesita ser drop-target además de clickeable; el botón "explorar…" interno provee la ruta accesible.
      // biome-ignore lint/a11y/useKeyWithClickEvents: la activación con teclado va por el botón explorar interno.
      onClick={open}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") open();
      }}
    >
      <div className="dropzone__icon">↓</div>
      <div className="dropzone__main">{label}</div>
      {sub ? <div className="dropzone__sub">{sub}</div> : null}
      {showBrowseButton ? (
        <button
          type="button"
          className="btn sm"
          onClick={(e) => {
            e.stopPropagation();
            open();
          }}
          disabled={disabled}
        >
          o explorar…
        </button>
      ) : null}
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={onChange}
        style={{ display: "none" }}
      />
    </div>
  );
}
