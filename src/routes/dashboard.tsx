import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  ClipboardPen,
  CreditCard,
  Loader2,
  MoreVertical,
  Pencil,
  Plus,
  RotateCcw,
  Search,
  Trash2,
  User,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
} from "@/components/ui/alert-dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AppHeader } from "@/components/AppHeader";
import { EmployeeFormDialog } from "@/components/EmployeeFormDialog";
import { WorkEntryDialog } from "@/components/WorkEntryDialog";
import { ManageWageDialog } from "@/components/ManageWageDialog";
import { RecordPaymentDialog } from "@/components/RecordPaymentDialog";
import { bigInput } from "@/components/shared";
import { useAppState } from "@/hooks/useAppState";
import { authService } from "@/services/authService";
import { employeeService } from "@/services/employeeService";
import { wageService } from "@/services/wageService";
import { workRecordService } from "@/services/workRecordService";
import type { DashboardFinancialSummary, Employee, EmployeeBalanceSummary, WorkRecord } from "@/types";
import { formatINR, formatLongToday, formatWage } from "@/utils/format";
import { cn } from "@/lib/utils";

const employeeActionBtn =
  "h-auto min-h-10 w-full py-2 px-1.5 text-xs leading-snug whitespace-normal sm:text-sm [&_svg]:size-4";

function EmployeeCardActions({
  employeeId,
  showWorkEntry,
  onWorkEntry,
  onRecordPayment,
  paymentLoading,
  showRecordPayment = true,
}: {
  employeeId: string;
  showWorkEntry?: boolean;
  onWorkEntry?: () => void;
  onRecordPayment: () => void;
  paymentLoading: boolean;
  showRecordPayment?: boolean;
}) {
  const showWork = Boolean(showWorkEntry && onWorkEntry);
  const showPay = showRecordPayment;
  const detailsSpansFullRow = (showWork && showPay) || (!showWork && !showPay);

  return (
    <div className="mt-3 grid grid-cols-2 gap-2">
      {showWork ? (
        <Button className={employeeActionBtn} onClick={onWorkEntry}>
          <ClipboardPen /> Enter Today&apos;s Work
        </Button>
      ) : null}
      {showPay ? (
        <Button className={employeeActionBtn} onClick={onRecordPayment} disabled={paymentLoading}>
          {paymentLoading ? <Loader2 className="animate-spin" /> : <CreditCard />}
          Record Payment
        </Button>
      ) : null}
      <Button
        variant="outline"
        className={cn(employeeActionBtn, detailsSpansFullRow && "col-span-2")}
        asChild
      >
        <Link to="/employees/$id" params={{ id: employeeId }}>
          <User /> View Details
        </Link>
      </Button>
    </div>
  );
}

export const Route = createFileRoute("/dashboard")({
  head: () => ({
    meta: [
      { title: "Employees — Daily Wage Calculator" },
      { name: "description", content: "Search employees, record today's work and manage wage rates." },
      { property: "og:title", content: "Employees — Daily Wage Calculator" },
      { property: "og:description", content: "Search employees, record today's work and manage wage rates." },
    ],
  }),
  component: Dashboard,
});

function Dashboard() {
  const navigate = useNavigate();
  const { state, ready } = useAppState();
  const [q, setQ] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [wageOpen, setWageOpen] = useState(false);
  const [editing, setEditing] = useState<Employee | undefined>();
  const [workFor, setWorkFor] = useState<Employee | null>(null);
  const [deleting, setDeleting] = useState<Employee | null>(null);
  const [activeTab, setActiveTab] = useState<"active" | "inactive">("active");

  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState<DashboardFinancialSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const [balances, setBalances] = useState<Record<string, EmployeeBalanceSummary>>({});
  const [balancesLoading, setBalancesLoading] = useState(false);
  const [balancesError, setBalancesError] = useState<string | null>(null);
  const [payingEmpId, setPayingEmpId] = useState<string | null>(null);
  const [payDialog, setPayDialog] = useState<{
    open: boolean;
    record: WorkRecord | null;
    records: WorkRecord[];
  }>({
    open: false,
    record: null,
    records: [],
  });

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setSummaryLoading(true);
    setBalancesLoading(true);
    setSummaryError(null);
    setBalancesError(null);

    let fetchedEmployees: Employee[] = [];
    try {
      const [emps] = await Promise.all([
        employeeService.fetchAll(),
        wageService.fetchGlobal().catch(() => {}),
      ]);
      fetchedEmployees = emps;
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load operational employee data.");
    } finally {
      setLoading(false);
    }

    try {
      const data = await employeeService.getFinancialSummary();
      setSummary(data);
    } catch (err) {
      setSummaryError(err instanceof Error ? err.message : "Failed to load financial summary from server.");
    } finally {
      setSummaryLoading(false);
    }

    try {
      const balMap = await employeeService.fetchAllBalances(
        fetchedEmployees.length > 0 ? fetchedEmployees : undefined,
      );
      setBalances(balMap);
    } catch (err) {
      setBalancesError(err instanceof Error ? err.message : "Failed to load employee balance summaries.");
    } finally {
      setBalancesLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!authService.isLoggedIn()) {
      navigate({ to: "/" });
      return;
    }
    loadDashboard();

    const handleUnauthorized = () => {
      navigate({ to: "/" });
      toast.error("Session expired. Please log in again.");
    };
    window.addEventListener("dwc:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("dwc:unauthorized", handleUnauthorized);
  }, [loadDashboard, navigate]);

  const handleRecordPaymentForEmployee = async (employeeId: string | number) => {
    const empIdStr = String(employeeId);
    const emp = state.employees.find((e) => e.id === empIdStr);
    if (!emp) return;

    setPayingEmpId(empIdStr);
    try {
      const records = await workRecordService.listForEmployee(empIdStr);
      const unpaid = records.filter(
        (r) =>
          (r.balanceDue !== undefined
            ? r.balanceDue
            : r.calculatedEarnings - (r.totalPaid ?? 0)) > 0,
      );
      if (unpaid.length === 0) {
        toast.info(`No unpaid work records found for ${emp.name}.`);
        return;
      }
      setPayDialog({
        open: true,
        record: unpaid[0] ?? null,
        records: unpaid,
      });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load work records for payment.");
    } finally {
      setPayingEmpId(null);
    }
  };

  const t = q.trim().toLowerCase();
  const activeEmployees = state.employees.filter((e) => e.isActive && e.name.toLowerCase().includes(t));
  const inactiveEmployees = state.employees.filter((e) => !e.isActive && e.name.toLowerCase().includes(t));
  return (
    <div className="min-h-dvh">
      <AppHeader />
      <main className="mx-auto max-w-5xl space-y-5 px-4 py-5">
        <section>
          <div className="flex min-w-0 items-center gap-2.5">
            <img
              src="/rupali-snacks-logo.png"
              alt=""
              width={44}
              height={44}
              decoding="async"
              className="size-9 shrink-0 object-contain sm:size-10 md:size-11"
            />
            <h1 className="min-w-0 truncate text-2xl font-bold">Rupali Snacks</h1>
          </div>
          <p className="mt-1 text-sm font-medium text-primary">{ready ? formatLongToday() : "\u00a0"}</p>
        </section>

        {/* Dashboard Financial Summary */}
        <section aria-label="Financial Overview" className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold">Financial Summary</h2>
            {summaryLoading && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
          </div>

          {summaryError && (
            <div className="flex items-center justify-between rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
              <span>{summaryError}</span>
              <Button variant="outline" size="sm" onClick={loadDashboard}>
                Retry
              </Button>
            </div>
          )}

          {!summaryError && summary && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              <div className="rounded-xl border-2 border-border bg-card p-3 shadow-card">
                <p className="text-xs text-muted-foreground sm:text-sm">Total Salary</p>
                <p className="break-words text-lg font-bold sm:text-xl">{formatINR(summary.totalEarnings)}</p>
              </div>
              <div className="rounded-xl border-2 border-border bg-card p-3 shadow-card">
                <p className="text-xs text-muted-foreground sm:text-sm">Total Paid</p>
                <p className="break-words text-lg font-bold text-success sm:text-xl">{formatINR(summary.totalPaid)}</p>
              </div>
              <div className="col-span-2 rounded-xl border-2 border-border bg-card p-3 shadow-card sm:col-span-1">
                <p className="text-xs text-muted-foreground sm:text-sm">Total Outstanding</p>
                <p className="break-words text-lg font-bold text-warning sm:text-xl">{formatINR(summary.outstandingBalance)}</p>
              </div>
            </div>
          )}
        </section>

        <div className="grid gap-3 sm:grid-cols-2">
          <Button size="xl" onClick={() => { setEditing(undefined); setAddOpen(true); }}><Plus /> Add Employee</Button>
          <Button size="xl" onClick={() => setWageOpen(true)}><Plus /> Add Wage</Button>
        </div>

        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-5 -translate-y-1/2 text-muted-foreground" />
          <input aria-label="Search employee" className={cn(bigInput, "h-14 pl-11 text-lg")} placeholder="Search employee by name..." value={q} onChange={(e) => setQ(e.target.value)} />
        </div>

        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "active" | "inactive")} className="space-y-4">
          <TabsList className="grid h-12 w-full grid-cols-2 rounded-xl bg-muted p-1">
            <TabsTrigger value="active" className="h-10 rounded-lg text-sm font-semibold">
              Active Employees ({activeEmployees.length})
            </TabsTrigger>
            <TabsTrigger value="inactive" className="h-10 rounded-lg text-sm font-semibold">
              Inactive Employees ({inactiveEmployees.length})
            </TabsTrigger>
          </TabsList>

          <TabsContent value="active" className="space-y-4">
            {ready && !loading && activeEmployees.length === 0 && (
              <p className="rounded-xl border-2 border-dashed border-border p-8 text-center text-muted-foreground">
                No active employees found.
              </p>
            )}

            <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {ready && activeEmployees.map((e) => (
                <li key={e.id} className="flex flex-col rounded-xl border-2 border-border bg-card p-3 shadow-card sm:p-4">
                  <div className="flex items-start justify-between gap-2">
                    <button type="button" onClick={() => setWorkFor(e)} className="min-w-0 text-left">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="break-words text-lg font-bold leading-snug">{e.name}</h2>
                        <span className="rounded-full border border-success/30 bg-success-soft px-2 py-0.5 text-xs font-semibold text-success">
                          Active
                        </span>
                      </div>
                      {e.workProfile && <p className="text-sm text-muted-foreground">Work profile: {e.workProfile}</p>}
                    </button>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" aria-label={`More options for ${e.name}`} className="-mr-2 -mt-1 size-10 shrink-0"><MoreVertical className="size-5" /></Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem className="py-2.5 text-base" onSelect={() => { setEditing(e); setAddOpen(true); }}><Pencil /> Edit</DropdownMenuItem>
                        <DropdownMenuItem className="py-2.5 text-base text-destructive" onSelect={() => setDeleting(e)}><Trash2 /> Delete</DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                  <p className="mt-2 text-sm sm:text-base">
                    Assigned wage: <span className="font-semibold">{formatWage(e.wageAmount, e.wageType)}</span>
                    <span className="ml-2 rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground">
                      {e.wageSource === "global" ? "Common" : "Individual"}
                    </span>
                  </p>
                  <EmployeeCardActions
                    employeeId={e.id}
                    showWorkEntry
                    onWorkEntry={() => setWorkFor(e)}
                    onRecordPayment={() => handleRecordPaymentForEmployee(e.id)}
                    paymentLoading={payingEmpId === e.id}
                  />
                </li>
              ))}
            </ul>
          </TabsContent>

          <TabsContent value="inactive" className="space-y-4">
            {ready && !loading && inactiveEmployees.length === 0 && (
              <p className="rounded-xl border-2 border-dashed border-border p-8 text-center text-muted-foreground">
                No inactive employees found.
              </p>
            )}

            <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {ready && inactiveEmployees.map((e) => {
                const b = balances[e.id];
                const outstanding = b?.outstandingBalance ?? 0;

                return (
                  <li key={e.id} className="flex flex-col rounded-xl border-2 border-border bg-card p-4 shadow-card">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <h2 className="break-words text-lg font-bold leading-snug">{e.name}</h2>
                          <span className="rounded-full border border-border bg-muted px-2 py-0.5 text-xs font-semibold text-muted-foreground">
                            Inactive
                          </span>
                        </div>
                        {e.workProfile && <p className="text-sm text-muted-foreground">Work profile: {e.workProfile}</p>}
                      </div>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" aria-label={`More options for ${e.name}`} className="-mr-2 -mt-1 size-10 shrink-0"><MoreVertical className="size-5" /></Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            className="py-2.5 text-base text-primary"
                            onSelect={async () => {
                              try {
                                await employeeService.activate(e.id);
                                toast.success(`Reactivated ${e.name}.`);
                                loadDashboard();
                              } catch (err) {
                                toast.error(err instanceof Error ? err.message : "Failed to reactivate employee.");
                              }
                            }}
                          >
                            <RotateCcw /> Reactivate Employee
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>

                    <p className="mt-2 text-base">
                      Wage reference: <span className="font-semibold">{formatWage(e.wageAmount, e.wageType)}</span>
                    </p>

                    <div className="mt-2 rounded-lg border border-border bg-muted/40 p-2.5 text-sm">
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Outstanding Balance:</span>
                        <span className={cn("text-base font-bold", outstanding > 0 ? "text-warning" : "text-muted-foreground")}>
                          {outstanding > 0 ? formatINR(outstanding) : "Settled (₹0.00)"}
                        </span>
                      </div>
                    </div>

                    <EmployeeCardActions
                      employeeId={e.id}
                      showWorkEntry={false}
                      onRecordPayment={() => handleRecordPaymentForEmployee(e.id)}
                      paymentLoading={payingEmpId === e.id}
                      showRecordPayment={outstanding > 0}
                    />
                  </li>
                );
              })}
            </ul>
          </TabsContent>
        </Tabs>

        {balancesError && (
          <p className="rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            Employee balance summaries could not be loaded. Payment actions may be limited until you refresh.
          </p>
        )}
      </main>

      <EmployeeFormDialog
        open={addOpen}
        onOpenChange={(o) => {
          setAddOpen(o);
          if (!o) loadDashboard();
        }}
        employee={editing}
      />
      <ManageWageDialog open={wageOpen} onOpenChange={setWageOpen} />
      <WorkEntryDialog
        open={!!workFor}
        onOpenChange={(o) => {
          if (!o) {
            setWorkFor(null);
            loadDashboard();
          }
        }}
        employee={workFor}
      />
      <RecordPaymentDialog
        open={payDialog.open}
        onOpenChange={(open) => setPayDialog((prev) => ({ ...prev, open }))}
        record={payDialog.record}
        records={payDialog.records}
        onSuccess={loadDashboard}
      />

      <AlertDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <AlertDialogContent className="w-[calc(100vw-1.5rem)] max-w-md rounded-xl">
          <AlertDialogHeader className="text-left">
            <AlertDialogTitle>Are you sure you want to delete this employee?</AlertDialogTitle>
            <AlertDialogDescription>{deleting?.name} will be hidden from the list. Past work records are kept.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="gap-2">
            <AlertDialogCancel className="h-12 text-base">Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="h-12 bg-destructive text-base text-destructive-foreground hover:bg-destructive/90"
              onClick={async () => {
                if (!deleting) return;
                try {
                  await employeeService.deactivate(deleting.id);
                  toast.success("Employee deleted.");
                  setDeleting(null);
                  loadDashboard();
                } catch (err) {
                  toast.error(err instanceof Error ? err.message : "Failed to delete employee.");
                }
              }}
            >
              Delete Employee
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
