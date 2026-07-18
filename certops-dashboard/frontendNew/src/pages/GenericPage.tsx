import React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function GenericPage({ title, content }: { title: string, content: string }) {
  return (
    <div className="min-h-screen bg-brand-bg flex items-center justify-center font-sans overflow-hidden">
      <div className="w-full max-w-2xl bg-white p-12 rounded-[32px] shadow-xl text-center relative">
        <Link to="/" className="absolute top-8 left-8 text-neutral-400 hover:text-brand-dark transition-colors">
          <ArrowLeft className="w-6 h-6" />
        </Link>
        <h1 className="text-4xl font-display font-bold tracking-tight text-brand-dark mb-6">{title}</h1>
        <p className="text-lg text-neutral-600 leading-relaxed mb-8">{content}</p>
        <Link to="/">
          <Button variant="lime" className="rounded-full font-bold px-8">Back to Home</Button>
        </Link>
      </div>
    </div>
  );
}
