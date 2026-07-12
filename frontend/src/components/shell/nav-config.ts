import {
  LayoutDashboard,
  Users,
  Briefcase,
  GitBranch,
  BellRing,
  MessageSquare,
  type LucideIcon,
} from "lucide-react";

import type { Role } from "@/lib/api/client";

export interface NavItem {
  title: string;
  href: string;
  icon: LucideIcon;
  roles?: Role[]; // undefined = all roles
  mock?: boolean; // screen backed by mock data, not the API
}

export const NAV_ITEMS: NavItem[] = [
  { title: "Overview", href: "/", icon: LayoutDashboard },
  { title: "Candidates", href: "/candidates", icon: Users },
  { title: "Jobs", href: "/jobs", icon: Briefcase },
  { title: "Applications", href: "/applications", icon: GitBranch },
  { title: "Needs attention", href: "/attention", icon: BellRing },
  {
    title: "Chat",
    href: "/chat",
    icon: MessageSquare,
    roles: ["admin", "recruiter"],
  },
];
