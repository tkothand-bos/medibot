import "./globals.css";

export const metadata = {
  title: "MediBot — MediAssist Health Network",
  description: "Internal intelligent assistant with role-based access control",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
