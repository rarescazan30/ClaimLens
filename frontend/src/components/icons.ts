import { Camera, CloudRain, Eye, FileCheck2, Inbox, Mountain, Newspaper, Satellite, Scale, ScanSearch, ShieldCheck, Stamp, Waves, Wind, Workflow, type LucideIcon } from 'lucide-react';
import type { AgentId, ClaimType, StageId } from '../lib/types';

export const STAGE_ICON: Record<StageId, LucideIcon> = {
  intake: Inbox,
  policy: ShieldCheck,
  plan: Workflow,
  agents: Workflow,
  judge: Scale,
  verdict: FileCheck2,
  review: Stamp,
};

export const AGENT_ICON: Record<AgentId, LucideIcon> = {
  meteo: CloudRain,
  satellite: Satellite,
  risk_zones: Mountain,
  photo_forensics: ScanSearch,
  street_view: Eye,
  news: Newspaper,
};

export const TYPE_ICON: Record<ClaimType, LucideIcon> = {
  flood: Waves,
  storm: Wind,
};

export const PHOTO_ICON = Camera;
