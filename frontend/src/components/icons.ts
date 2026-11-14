import {
  Camera,
  CloudRain,
  Eye,
  FileCheck2,
  FileText,
  Inbox,
  Mountain,
  Newspaper,
  Satellite,
  Scale,
  ScanSearch,
  ShieldCheck,
  Snowflake,
  Stamp,
  UserCheck,
  Waves,
  Wind,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import type { AgentId, ClaimType, StageId } from '../mock/types';

export const STAGE_ICON: Record<StageId, LucideIcon> = {
  intake: Inbox,
  client: UserCheck,
  documents: FileText,
  policy: ShieldCheck,
  photos: Camera,
  plan: Workflow,
  agents: Workflow,
  judge: Scale,
  verdict: FileCheck2,
  review: Stamp,
};

export const AGENT_ICON: Record<AgentId, LucideIcon> = {
  weather: CloudRain,
  satellite: Satellite,
  streetview: Eye,
  news: Newspaper,
  risk: Mountain,
  forensics: ScanSearch,
};

export const TYPE_ICON: Record<ClaimType, LucideIcon> = {
  flood: Waves,
  wind: Wind,
  landslide: Mountain,
  snow: Snowflake,
};
