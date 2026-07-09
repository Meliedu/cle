import { PageHeader } from "@/components/patterns";
import { SettingsView } from "@/components/settings/settings-view";

export default function TeacherProfilePage() {
  return (
    <div className="mx-auto w-full max-w-4xl space-y-8 px-6 py-6 md:px-10 md:py-10">
      <PageHeader
        title="Profile"
        description="Manage your account details, password, and how your name appears in your courses."
      />
      <SettingsView />
    </div>
  );
}
