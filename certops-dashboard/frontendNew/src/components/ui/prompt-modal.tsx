import * as React from "react"
import { X, AlertCircle, Info, CheckCircle2 } from "lucide-react"
import { Button } from "./button"

export interface PromptModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  children?: React.ReactNode;
  status?: "info" | "warning" | "success";
}

export function PromptModal({
  isOpen,
  onClose,
  title = "Feature Interaction",
  description = "This interaction is currently a placeholder or not fully implemented yet.",
  actionLabel,
  onAction,
  children,
  status = "info",
}: PromptModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in-0">
      <div 
        className="bg-white rounded-3xl p-6 shadow-2xl border border-neutral-100 max-w-md w-full mx-auto relative animate-in zoom-in-95"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
              status === "warning" 
                ? "bg-amber-50 text-amber-600" 
                : status === "success" 
                ? "bg-brand-lime/30 text-brand-dark" 
                : "bg-brand-purple/20 text-brand-purple"
            }`}>
              {status === "warning" && <AlertCircle className="w-5 h-5" />}
              {status === "success" && <CheckCircle2 className="w-5 h-5" />}
              {status === "info" && <Info className="w-5 h-5" />}
            </div>
            <div>
              <h3 className="font-display font-bold text-lg text-brand-dark leading-tight">{title}</h3>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="text-neutral-400 hover:text-neutral-700 transition-colors p-1 rounded-full hover:bg-neutral-100"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="text-sm font-medium text-neutral-600 mb-6 pl-13">
          {description && <p className="mb-4">{description}</p>}
          {children}
        </div>

        <div className="flex items-center justify-end gap-3 pt-2 border-t border-neutral-100">
          <Button variant="outline" size="sm" onClick={onClose} className="rounded-full font-bold">
            Close
          </Button>
          {actionLabel && onAction && (
            <Button variant="lime" size="sm" onClick={onAction} className="rounded-full font-bold">
              {actionLabel}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
