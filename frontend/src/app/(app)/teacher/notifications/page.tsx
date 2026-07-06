import { PageHeader } from "@/components/patterns";
import { NotificationPreferencesForm } from "@/components/settings/notification-preferences-form";

export default function TeacherNotificationsPage() {
  return (
    <div className="mx-auto w-full max-w-4xl space-y-8 px-6 py-6 md:px-10 md:py-10">
      <PageHeader
        title="Notifications"
        description="Decide which reminders and alerts Meli sends you — without the noise."
      />
      <NotificationPreferencesForm />
    </div>
  );
}
