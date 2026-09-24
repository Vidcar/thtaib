import type { SchemaHubVariant } from "../generated/shared-contracts/openapi";

export type VariantPresentation = { variant: SchemaHubVariant; quant: string; bits: number | null; family: string; flavour: "Standard" | "LOW-MTP" | "MTP" };

export function presentVariant(variant: SchemaHubVariant): VariantPresentation {
  const stem = variant.name.split("/").at(-1)?.replace(/\.gguf$/i, "") ?? "";
  const parts = stem.split("-");
  const token = [...parts].reverse().find(part => /^(?:IQ\d(?:_[A-Za-z0-9]+)*|Q\d(?:_[A-Za-z0-9]+)*|BF16|FP16|FP32|F16|F32)$/i.test(part));
  const index = token ? parts.lastIndexOf(token) : -1;
  const quant = token ? `${index > 0 && parts[index - 1].toUpperCase() === "UD" ? "UD-" : ""}${token.toUpperCase()}` : "Unknown";
  const bitMatch = quant.match(/^(?:UD-)?I?Q(\d+)/);
  const bits = bitMatch ? Number(bitMatch[1]) : /^(?:BF16|FP16|F16)$/.test(quant) ? 16 : /^(?:FP32|F32)$/.test(quant) ? 32 : null;
  const suffix = parts.slice(Math.max(0, index - 2), index).join("-").toUpperCase();
  const flavour = suffix === "LOW-MTP" ? "LOW-MTP" : suffix.endsWith("MTP") && parts[index - 1]?.toUpperCase() === "MTP" ? "MTP" : "Standard";
  return { variant, quant, bits, family: bits == null ? "Unknown" : `${bits}-bit`, flavour };
}

export function variantFamilies(variants: SchemaHubVariant[], bitFilter: number | "all" | "unknown", sizeOrder: "asc" | "desc") {
  const shown = variants.map(presentVariant).filter(item => bitFilter === "all" || (bitFilter === "unknown" ? item.bits == null : item.bits === bitFilter));
  const groups = new Map<string, VariantPresentation[]>();
  for (const item of shown) groups.set(item.family, [...(groups.get(item.family) ?? []), item]);
  return [...groups.entries()].sort(([a], [b]) => a === "Unknown" ? 1 : b === "Unknown" ? -1 : Number.parseInt(a) - Number.parseInt(b)).map(([family, items]) => ({
    family,
    items: items.sort((a, b) => (a.variant.size_bytes == null && b.variant.size_bytes == null ? 0 : a.variant.size_bytes == null ? 1 : b.variant.size_bytes == null ? -1 : (a.variant.size_bytes - b.variant.size_bytes) * (sizeOrder === "asc" ? 1 : -1)) || a.quant.localeCompare(b.quant)),
  }));
}
