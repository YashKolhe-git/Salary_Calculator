import { useNavigate } from "@tanstack/react-router";
import { LogOut, Wallet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { authService } from "@/services/authService";

export function AppHeader() {
  const navigate = useNavigate();
  return (
    <header className="sticky top-0 z-30 border-b-2 border-border bg-card shadow-sm">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
        <div className="flex items-center gap-2 font-bold">
          <Wallet className="size-5 text-primary" /> Daily Wage Calculator
        </div>
        <Button
          variant="outline"
          onClick={async () => {
            await authService.logout();
            navigate({ to: "/" });
          }}
        >
          <LogOut /> Logout
        </Button>
      </div>
    </header>
  );
}
